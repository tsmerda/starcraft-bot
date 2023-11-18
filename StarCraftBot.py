import random
from sc2 import maps
from sc2.bot_ai import BotAI
from sc2.data import Race, Difficulty
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId
from sc2.main import run_game
from sc2.player import Bot, Computer


class StarCraftBot(BotAI):
    def __init__(self):
        super().__init__()

        self.last_expansion_attempt = -999
        self.EXPANSION_LIMIT = 4  # Max number of expansions
        self.MINERALS_FOR_EXPANSION = 400  # Amount of minerals to be saved for expansion
        self.EXPANSION_COOLDOWN = 100  # Cooldown (game steps) between expansions to avoid over-expanding

    async def on_step(self, iteration: int):
        if iteration == 0:
            await self.send_scout()

        # if iteration % 50 == 0:
        #     await self.check_and_relocate_workers()

        # Send scout every 5 minutes
        if self.state.game_loop % (10 * 60 * 22.4) == 0:
            await self.send_scout()

        # Try to defend if under attack, otherwise proceed with normal strategy
        if not await self.defend():
            # Regular strategy execution
            await self.manage_economy()
            await self.manage_army()
            await self.attacking_strategy()
            # await self.manage_siege_tanks()

        await self.build_offensive_force()

        # Method to manage economic development such as building workers and expanding

    async def manage_economy(self):
        await self.distribute_workers()
        await self.build_workers()
        await self.manage_expansion()
        await self.build_supply_depots()
        await self.build_refinery()
        await self.build_engineering_bay()
        await self.build_defensive_structures()
        await self.build_techlab()

    # Method to manage army building and tech progression
    async def manage_army(self):
        await self.manage_production_buildings()
        await self.upgrade_units()
        await self.upgrade_structures()

    # Method to manage attacks and army movement
    async def attacking_strategy(self):
        attack_force_size = 32
        offensive_units = {UnitTypeId.MARINE,
                           UnitTypeId.REAPER,
                           UnitTypeId.MARAUDER,
                           UnitTypeId.MEDIVAC,
                           UnitTypeId.BANSHEE,
                           UnitTypeId.SIEGETANK}
        total_offensive_units = sum(self.units(unit_type).amount for unit_type in offensive_units)

        if total_offensive_units >= attack_force_size:
            target = self.find_target()
            for unit_type in offensive_units:
                for unit in self.units(unit_type).idle:
                    unit.attack(target)

    def find_target(self):
        if self.enemy_units:
            return random.choice(self.enemy_units)
        elif self.enemy_structures:
            return random.choice(self.enemy_structures)
        else:
            return self.enemy_start_locations[0]

    # Send out the initial scout worker at the start of the game
    async def send_scout(self):
        worker = self.workers.random
        worker.move(self.enemy_start_locations[0])

    # SCV production across all command centers
    async def build_workers(self):
        early_game_scv_limit = 22
        mid_game_scv_limit = 40
        late_game_scv_limit = 60

        if self.minutes_passed < 5:
            scv_limit = early_game_scv_limit
        elif self.minutes_passed < 10:
            scv_limit = mid_game_scv_limit
        else:
            scv_limit = late_game_scv_limit

        ideal_scv_per_cc = 16
        if self.workers.amount < min(ideal_scv_per_cc * self.townhalls.amount, scv_limit) and self.supply_left > 0:
            for cc in self.townhalls.ready.idle:
                if self.can_afford(UnitTypeId.SCV):
                    cc.train(UnitTypeId.SCV)

    # Ensure we are not supply capped by building supply depots
    async def build_supply_depots(self):
        if self.supply_left < 8 and not self.already_pending(UnitTypeId.SUPPLYDEPOT):
            ccs = self.townhalls.ready
            if ccs.exists and self.can_afford(UnitTypeId.SUPPLYDEPOT):
                location = await self.find_placement(
                    UnitTypeId.SUPPLYDEPOT, self.main_base_ramp.barracks_correct_placement,
                    max_distance=15, random_alternative=False, placement_step=2
                )
                if location:
                    await self.build_building_near(UnitTypeId.SUPPLYDEPOT, location)

    # Logic for expanding to a new base
    async def manage_expansion(self):
        if self.townhalls.ready.amount < self.EXPANSION_LIMIT:
            # Fast first expansion regardless of cooldown
            if self.townhalls.ready.amount == 1 and self.minerals > self.MINERALS_FOR_EXPANSION:
                location = await self.get_next_expansion()
                if location:
                    err = await self.expand_now()
                    if not err:
                        self.last_expansion_attempt = self.time

            # Check if we're not on cooldown from the last attempted expansion
            elif self.time - self.last_expansion_attempt > self.EXPANSION_COOLDOWN:
                # Check if we have saved enough minerals for an expansion
                if self.minerals > self.MINERALS_FOR_EXPANSION:
                    # Find the location for the next expansion
                    location = await self.get_next_expansion()
                    # Ensure that there are no nearby enemies before trying to expand
                    if location and not self.enemy_units.closer_than(10, location).exists:
                        err = await self.expand_now()
                        if not err:
                            self.last_expansion_attempt = self.time

    # TODO: -- Managing relocation of workers
    # async def check_and_relocate_workers(self):
    #     # Checking if some raw material sources are exhausted
    #     for cc in self.townhalls.ready:
    #         minerals_close = self.mineral_field.closer_than(10.0, cc)
    #         if not minerals_close:
    #             # If there are no more minerals near the command center, move the SCV
    #             new_location = self.find_new_resource_location()
    #             if new_location:
    #                 for scv in self.workers.closer_than(10.0, cc):
    #                     self.do(scv.move(new_location))
                    
    # async def find_new_resource_location(self):
    #     # Finding the nearest unoccupied expansion
    #     closest_expansion = None
    #     min_distance = float('inf')
    #     for expansion in self.expansion_locations:
    #         # If the expansion is already occupied, skip it
    #         if any(cc.position.is_same_as(expansion) for cc in self.townhalls):
    #             continue
    #         # Calculating distance from current position
    #         distance = self.start_location.distance_to(expansion)
    #         if distance < min_distance:
    #             min_distance = distance
    #             closest_expansion = expansion
    #     return closest_expansion

    # Building refineries at each base to collect vespene gas
    async def build_refinery(self):
        for cc in self.townhalls.ready:
            # Find all Vespenes within a reasonable distance to our ready TownHalls
            vespenes = self.vespene_geyser.closer_than(10, cc)
            for vespene in vespenes:
                # Check if we don't have a refinery and we're not already building a refinery here
                if not self.gas_buildings.closer_than(1.0, vespene).exists and self.already_pending(
                        UnitTypeId.REFINERY) == 0:
                    if self.can_afford(UnitTypeId.REFINERY):
                        await self.build(UnitTypeId.REFINERY, vespene)

            # Make sure we don't build excess Refineries
        if self.gas_buildings.amount < self.townhalls.ready.amount * 2:
            for cc in self.townhalls.ready:
                # Find the closest Vespene Geyser without an active Refinery
                vespene = self.vespene_geyser.closest_to(cc)
                if self.can_afford(UnitTypeId.REFINERY) and not self.gas_buildings.closer_than(1.0, vespene).exists:
                    await self.build(UnitTypeId.REFINERY, vespene)

    # Create and manage production buildings
    async def manage_production_buildings(self):
        max_factories = 2
        max_starports = 3 if self.minutes_passed < 7 else 4
        max_barracks = 3 if self.minutes_passed < 7 else 4
        max_armories = 2

        if self.structures(UnitTypeId.SUPPLYDEPOT).ready.exists:
            # Create production buildings based on requirements for your chosen army composition
            barracks_count = self.structures(UnitTypeId.BARRACKS).amount
            factory_count = self.structures(UnitTypeId.FACTORY).amount
            starport_count = self.structures(UnitTypeId.STARPORT).amount
            armory_count = self.structures(UnitTypeId.ARMORY).amount

            # Check if building is in progress 
            # barracks_in_progress = self.already_pending(UnitTypeId.BARRACKS)
            # factory_in_progress = self.already_pending(UnitTypeId.FACTORY)
            # starport_in_progress = self.already_pending(UnitTypeId.STARPORT)
            # armory_in_progress = self.already_pending(UnitTypeId.ARMORY)

            # Requirements for building production structures
            need_more_barracks = self.can_afford(UnitTypeId.BARRACKS) and barracks_count < max_barracks
            need_more_factories = self.can_afford(UnitTypeId.FACTORY) and factory_count < max_factories
            need_more_starports = self.can_afford(UnitTypeId.STARPORT) and starport_count < max_starports
            # TODO: -- NOT WORKING
            need_armory = self.can_afford(
                UnitTypeId.ARMORY) and armory_count < max_armories and factory_count > 0  # Build Armory after the first Factory

            # Logic to build Barracks, Factories, Starports, and an Armory
            if need_more_barracks:
                await self.build_building_near(UnitTypeId.BARRACKS, self.start_location)

            if need_more_factories and barracks_count > 0:  # Ensure we have a Barracks before building a Factory
                await self.build_building_near(UnitTypeId.FACTORY, self.start_location)

            if need_more_starports and factory_count > 0:  # Ensure we have a Factory before building a Starport
                await self.build_building_near(UnitTypeId.STARPORT, self.start_location)

            if need_armory:
                await self.build_building_near(UnitTypeId.ARMORY, self.start_location)

    # Produce combat units from available barracks
    async def build_offensive_force(self):
        # Logic to determine the number of each type of unit to have at different stages of the game
        marine_count_target = 14 if self.minutes_passed < 10 else 16
        marauder_count_target = 14 if self.minutes_passed < 10 else 16
        medivac_count_target = 4 if self.minutes_passed < 10 else 6
        banshee_count_target = 2 if self.minutes_passed < 10 else 4
        reaper_count_target = 4 if self.minutes_passed < 5 else 0
        siege_tank_count_target = 6 if self.minutes_passed < 10 else 8

        # Check if we have the required buildings before training units
        barracks_ready = self.structures(UnitTypeId.BARRACKS).ready.exists
        factory_ready = self.structures(UnitTypeId.FACTORY).ready.exists
        starport_ready = self.structures(UnitTypeId.STARPORT).ready.exists

        # Training logic for each unit type based on available buildings and resources
        if barracks_ready:
            for rax in self.structures(UnitTypeId.BARRACKS).ready.idle:
                if self.can_afford(UnitTypeId.MARINE) and self.units(UnitTypeId.MARINE).amount + self.already_pending(UnitTypeId.MARINE) < marine_count_target:
                    rax.train(UnitTypeId.MARINE)

                # Include a check to see if a Tech Lab is attached for Marauders and if we've hit our target count
                elif self.can_afford(UnitTypeId.MARAUDER) and rax.has_add_on and self.units(
                        UnitTypeId.MARAUDER).amount + self.already_pending(UnitTypeId.MARAUDER) < marauder_count_target:
                    rax.train(UnitTypeId.MARAUDER)

                # Reaper training prioritized early game for harassment
                if self.can_afford(UnitTypeId.REAPER) and self.units(UnitTypeId.REAPER).amount + self.already_pending(UnitTypeId.REAPER) < reaper_count_target:
                    rax.train(UnitTypeId.REAPER)

        # Factory for Siege Tanks
        if factory_ready:
            for factory in self.structures(UnitTypeId.FACTORY).ready.idle:
                if self.units(UnitTypeId.SIEGETANK).amount < siege_tank_count_target and self.can_afford(
                        UnitTypeId.SIEGETANK):
                    factory.train(UnitTypeId.SIEGETANK)

        # Starport for Medivacs and Banshees
        if starport_ready:
            for starport in self.structures(UnitTypeId.STARPORT).ready.idle:
                if self.units(UnitTypeId.MEDIVAC).amount < medivac_count_target and self.can_afford(UnitTypeId.MEDIVAC):
                    starport.train(UnitTypeId.MEDIVAC)
                # Check if techlab is attached for Banshee production
                if starport.has_add_on and self.can_afford(UnitTypeId.BANSHEE) and self.units(
                        UnitTypeId.BANSHEE).amount < banshee_count_target:
                    starport.train(UnitTypeId.BANSHEE)

    # Engineering bay for upgrade research
    async def upgrade_units(self):
        if self.structures(UnitTypeId.ENGINEERINGBAY).ready.exists:
            if self.can_afford(UpgradeId.TERRANINFANTRYWEAPONSLEVEL1) and not self.already_pending_upgrade(
                    UpgradeId.TERRANINFANTRYWEAPONSLEVEL1):
                self.structures(UnitTypeId.ENGINEERINGBAY).ready.first.research(
                    UpgradeId.TERRANINFANTRYWEAPONSLEVEL1)
            if self.can_afford(UpgradeId.TERRANINFANTRYARMORSLEVEL1) and not self.already_pending_upgrade(
                    UpgradeId.TERRANINFANTRYARMORSLEVEL1):
                self.structures(UnitTypeId.ENGINEERINGBAY).ready.first.research(                        UpgradeId.TERRANINFANTRYARMORSLEVEL1) 
        if self.structures(UnitTypeId.ARMORY).ready.exists:
            if self.can_afford(UpgradeId.TERRANVEHICLEARMORSLEVEL1) and not self.already_pending_upgrade(
                        UpgradeId.TERRANVEHICLEARMORSLEVEL1):
                    self.structures(UnitTypeId.ENGINEERINGBAY).ready.first.research(
                        UpgradeId.TERRANVEHICLEARMORSLEVEL1)
            if self.can_afford(UpgradeId.TERRANSHIPWEAPONSLEVEL1) and not self.already_pending_upgrade(
                        UpgradeId.TERRANSHIPWEAPONSLEVEL1):
                    self.structures(UnitTypeId.ENGINEERINGBAY).ready.first.research(
                        UpgradeId.TERRANSHIPWEAPONSLEVEL1)
            if self.can_afford(UpgradeId.TERRANVEHICLEANDSHIPARMORSLEVEL1) and not self.already_pending_upgrade(
                        UpgradeId.TERRANVEHICLEANDSHIPARMORSLEVEL1):
                    self.structures(UnitTypeId.ENGINEERINGBAY).ready.first.research(
                        UpgradeId.TERRANVEHICLEANDSHIPARMORSLEVEL1)
            if self.can_afford(UpgradeId.TERRANVEHICLEANDSHIPWEAPONSLEVEL1) and not self.already_pending_upgrade(
                        UpgradeId.TERRANVEHICLEANDSHIPWEAPONSLEVEL1):
                    self.structures(UnitTypeId.ENGINEERINGBAY).ready.first.research(
                        UpgradeId.TERRANVEHICLEANDSHIPWEAPONSLEVEL1)
                    
    async def upgrade_structures(self):
       if self.structures(UnitTypeId.ENGINEERINGBAY).ready.exists:
            if self.can_afford(UpgradeId.TERRANBUILDINGARMOR) and not self.already_pending_upgrade(UpgradeId.TERRANBUILDINGARMOR):
                self.structures(UnitTypeId.ENGINEERINGBAY).ready.first.research(UpgradeId.TERRANBUILDINGARMOR)   
            if self.can_afford(UpgradeId.HISECAUTOTRACKING) and not self.already_pending_upgrade(UpgradeId.HISECAUTOTRACKING):
                self.structures(UnitTypeId.ENGINEERINGBAY).ready.first.research(UpgradeId.HISECAUTOTRACKING) 

                    # orbital command
                    # planatary fortress  

    # Develop the base's technology with tech labs
    async def build_techlab(self):
        # Check if we have enough resources to build a Tech Lab
        if self.can_afford(UnitTypeId.BARRACKSTECHLAB):
            # Iterate through all Barracks without a Tech Lab
            for rax in self.structures(UnitTypeId.BARRACKS).ready:
                if not rax.has_add_on:
                    # Attach a Tech Lab to the Barracks
                    rax.build(UnitTypeId.BARRACKSTECHLAB)

        # Similarly, build Tech Labs for Factories and Starports if needed
        if self.can_afford(UnitTypeId.FACTORYTECHLAB):
            for factory in self.structures(UnitTypeId.FACTORY).ready:
                if not factory.has_add_on:
                    factory.build(UnitTypeId.FACTORYTECHLAB)

        if self.can_afford(UnitTypeId.STARPORTTECHLAB):
            for starport in self.structures(UnitTypeId.STARPORT).ready:
                if not starport.has_add_on:
                    starport.build(UnitTypeId.STARPORTTECHLAB)

    # Use established position logic to prevent unit pathing blockage
    async def build_building_near(self, building_type, near_structure, max_distance=20):
        # Note that try...except blocks are used to handle the situation where the bot may be unable to find a
        # valid build location (e.g. all locations are blocked or currently occupied).
        try:
            location = await self.find_placement(building_type, near_structure.position, max_distance=max_distance)
            if location:
                workers = self.workers.gathering
                if workers:  # Ensure we have workers to use
                    worker = workers.closest_to(location)
                    worker.build(building_type, location)
                    return True  # Successfully found a location and issued a build command
        except Exception as e:
            print(str(e))  # For debugging purposes, remove or handle this print as desired in production
        return False  # Failed to find a location/build the structure

    async def build_engineering_bay(self):
        # Check if you already have an ENGINEERINGBAY
        if not self.structures(UnitTypeId.ENGINEERINGBAY).exists:
            # Ensure you have enough resources before trying to build
            if self.can_afford(UnitTypeId.ENGINEERINGBAY):
                # Pick the location near a Command Center or another suitable place
                location = await self.find_placement(UnitTypeId.ENGINEERINGBAY,
                                                     near=self.start_location.towards(self.game_info.map_center, 5))
                if location:
                    await self.build_building_near(UnitTypeId.ENGINEERINGBAY, location)

    async def build_defensive_structures(self):
        # if self.structures(UnitTypeId.ENGINEERINGBAY).ready.exists:
        #     for cc in self.townhalls.ready:
        #         await self.build_missile_turrets(cc)

        for cc in self.townhalls.ready:
            await self.build_bunkers(cc)

    # TODO: -- NOT WORKING
    # async def build_missile_turrets(self, cc):
    #     if self.structures(UnitTypeId.MISSILETURRET).closer_than(10, cc).amount < 2 and self.can_afford(UnitTypeId.MISSILETURRET):
    #         location = await self.find_placement(UnitTypeId.MISSILETURRET, cc.position.towards(self.game_info.map_center, 10))
    #         if location:
    #             await self.build_building_near(UnitTypeId.MISSILETURRET, location)

    async def build_bunkers(self, cc):
         if self.structures(UnitTypeId.BUNKER).closer_than(10, cc).amount < 2 and self.can_afford(UnitTypeId.BUNKER):
            location = await self.find_placement(UnitTypeId.BUNKER, cc.position.towards(self.game_info.map_center, 10))
            if location:
                await self.build_building_near(UnitTypeId.BUNKER, location)

    async def defend(self):
        for th in self.townhalls:
            enemies = self.enemy_units.closer_than(30, th.position)
            if enemies.exists:
                defensive_squad = self.units.idle
                self.defend_base(th, enemies, defensive_squad)
                return True
        return False

    def defend_base(self, location, enemies, defensive_squad):
        if enemies.exists:
            # If the idle defensive squad is smaller than the minimum defense squad, get more units
            if defensive_squad.amount < 5:
                backup_units = defensive_squad.prefer_idle.idle  # Get both idle and engaged units close to base
                for unit in backup_units:
                    unit.attack(enemies.closest_to(location))
            else:
                # Otherwise, use the idle defensive squad
                for unit in defensive_squad:
                    unit.attack(enemies.closest_to(location))

    # async def manage_siege_tanks(self):
    #     siege_mode_distance = 13
    #     for tank in self.units(UnitTypeId.SIEGETANK).idle:
    #         # Find the closest enemy
    #         closest_enemy = self.known_enemy_units.closest_to(tank.position)

    #         if closest_enemy and tank.distance_to(closest_enemy) <= siege_mode_distance:
    #             # Siege up if not already in siege mode and enemy is within range
    #             if not tank.has_buff(UnitTypeId.SIEGETANKSIEGED):
    #                 await self.do(tank(UnitTypeId.OBSERVERSIEGEMODE))
    #         else:
    #             # Unsiege if sieged and no enemies are within the specified range
    #             if tank.has_buff(UnitTypeId.SIEGETANKSIEGED):
    #                 await self.do(tank(UnitTypeId.OVERSEERSIEGEMODE))

    # Calculate elapsed game time minutes
    @property
    def minutes_passed(self):
        return self.state.game_loop / (22.4 * 60)


# Run the game
run_game(
    maps.get("sc2-ai-cup-2022"),
    [Bot(Race.Terran, StarCraftBot()), Computer(Race.Terran, Difficulty.Medium)],
    realtime=False,
)
