import random

from sc2 import maps
from sc2.bot_ai import BotAI
from sc2.data import Race, Difficulty
from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId
from sc2.main import run_game
from sc2.player import Bot, Computer


class StarCraftBot(BotAI):
    def __init__(self):
        super().__init__()

        self.last_expansion_attempt = -999
        self.EXPANSION_LIMIT = 3  # Max number of expansions
        self.MINERALS_FOR_EXPANSION = 100  # Amount of minerals to be saved for expansion
        self.EXPANSION_COOLDOWN = 150  # Cooldown (game steps) between expansions to avoid over-expanding
        self.INITIAL_SCOUT_SENT = False
        self.rally_point = None

    async def on_step(self, iteration: int):
        if iteration % 100 == 0:
            await self.check_and_relocate_workers()

        await self.scouting_strategy()

        if self.minutes_passed < 1:
            await self.manage_economy()
        else:
            # Try to defend if under attack, otherwise proceed with normal strategy
            if not await self.defend():
                # Regular strategy execution
                await self.manage_economy()
                await self.manage_army()
                await self.attacking_strategy()
                # Continuous scouting
                if iteration % 3000 == 0:
                    await self.continuous_scouting()
                # Update rally point periodically or when necessary
                if iteration % 500 == 0 or not self.rally_point:
                    self.rally_point = self.choose_rally_point()
                # Regroup idle military units at the rally point
                await self.regroup_at_rally_point()

            await self.build_offensive_force()
            await self.manage_army_micro()

    # Method to manage economic development such as building workers and expanding
    async def manage_economy(self):
        await self.distribute_workers()
        await self.build_workers()
        await self.manage_expansion()
        if self.minutes_passed > 1:
            await self.build_supply_depots()
            await self.build_refinery()
            await self.build_engineering_bay()
            await self.build_techlab()

    # Method to manage army building and tech progression
    async def manage_army(self):
        await self.manage_production_buildings()
        await self.upgrade_units()
        await self.upgrade_structures()

    # Method to manage attacks and army movement
    async def attacking_strategy(self):
        # Gather offensive units
        army_units = self.units.filter(
            lambda unit: unit.type_id in {UnitTypeId.MARINE, UnitTypeId.MARAUDER, UnitTypeId.REAPER,
                                          UnitTypeId.SIEGETANK, UnitTypeId.SIEGETANKSIEGED}
        )
        medivacs = self.units(UnitTypeId.MEDIVAC)

        # Check army size to see if it's time to attack
        attack_force_size = 20 if self.minutes_passed < 10 else 32
        if army_units.amount >= attack_force_size:
            # Find a target
            target = self.find_target()

            # Additional logic to decide whether to continue the attack or retreat
            await self.decide_attack_or_retreat(target, army_units, medivacs)

    async def decide_attack_or_retreat(self, target, army_units, medivacs):
        # Calculate our strength and the enemy's strength
        our_strength = self.calculate_army_strength(army_units)
        enemy_strength = self.calculate_enemy_strength(target)

        # If our strength is significantly higher, continue the attack
        if our_strength > enemy_strength * 1.2:
            for unit in army_units:
                unit.attack(target)
            for medivac in medivacs:
                medivac.move(army_units.closest_to(target))
        # If the enemy is stronger, retreat to a safe location
        elif our_strength < enemy_strength:
            safe_location = self.start_location
            for unit in army_units:
                unit.move(safe_location)
            for medivac in medivacs:
                medivac.move(safe_location)

    def calculate_army_strength(self, army_units):
        # A simple calculation based on unit types and their health
        strength = 0
        for unit in army_units:
            strength += unit.health + unit.shield
        return strength

    def calculate_enemy_strength(self, target):
        # A simple calculation based on visible enemy units near the target
        enemy_units = self.enemy_units.closer_than(15, target)
        strength = 0
        for enemy in enemy_units:
            strength += enemy.health + enemy.shield
        return strength

    def find_target(self):
        # Check for visible enemy units or structures
        if self.enemy_units:
            return random.choice(self.enemy_units).position
        if self.enemy_structures:
            return random.choice(self.enemy_structures).position

        # If no enemy is visible, iterate over the potential expansion locations
        for location in self.expansion_locations_list:
            # Check if we've already explored this location
            if self.is_visible(location):
                # If there's nothing here, and we've seen it, move on
                continue
            # We haven't seen this place, so let's go take a look
            return location

        # As a last resort, if we have no visible enemy and all expansions have been scouted with nothing found,
        # just return the enemy start location (it's likely incorrect if the game has gone on this long but better
        # than nothing)
        return random.choice(self.enemy_start_locations)

    # scouting logic
    async def scouting_strategy(self):
        # Initial worker scout
        if not self.INITIAL_SCOUT_SENT:
            await self.send_initial_scout()

        # Use scans or other abilities for additional information if necessary
        await self.use_scanning_abilities()

    async def send_initial_scout(self):
        # Send a worker to scout enemy bases at the start of the game
        if self.workers.exists:
            scout = self.workers.random
            for location in self.enemy_start_locations:
                scout.move(location)
            self.INITIAL_SCOUT_SENT = True

    async def continuous_scouting(self):
        if self.workers.exists:
            scout = self.workers.random
            for location in self.enemy_start_locations:
                scout.move(location)

    async def use_scanning_abilities(self):
        # Use Orbital Command's Scanner Sweep to gain vision if we have enough energy
        if self.units(UnitTypeId.ORBITALCOMMAND).exists:
            for oc in self.units(UnitTypeId.ORBITALCOMMAND).filter(lambda x: x.energy >= 50):
                # Find a priority target for scanning, such as enemy army or hidden expansions
                scan_target = random.choice(self.enemy_start_locations)
                if scan_target:
                    oc(AbilityId.SCAN_MOVE, scan_target)
                    break

    # SCV production across all command centers
    async def build_workers(self):
        if self.minutes_passed < 2:
            ideal_scv_per_cc = 8
        else:
            ideal_scv_per_cc = 12
        if self.workers.amount < ideal_scv_per_cc * self.townhalls.amount and self.supply_left > 0:
            for cc in self.townhalls.ready.idle:
                if self.can_afford(UnitTypeId.SCV):
                    cc.train(UnitTypeId.SCV)

    # Ensure we are not supply capped by building supply depots
    async def build_supply_depots(self):
        if self.supply_left < 10 and not self.already_pending(UnitTypeId.SUPPLYDEPOT):
            ccs = self.townhalls.ready
            if ccs.exists and self.can_afford(UnitTypeId.SUPPLYDEPOT):
                await self.build_building_near(UnitTypeId.SUPPLYDEPOT, random.choice(ccs).position)

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

    async def check_and_relocate_workers(self):
        for cc in self.townhalls.ready:
            # Are there still resources close to this Command Center to gather from?
            minerals_close = self.mineral_field.closer_than(10, cc)
            geysers_close = self.vespene_geyser.closer_than(10, cc)
            if minerals_close and geysers_close:
                # There are still resources around, no need for relocation
                continue

            # Time to find a new mining location as current resources are depleted
            new_location = await self.find_new_resource_location()
            if new_location:
                # Relocate the workers from depleted resources to the new location
                for scv in self.workers.idle or self.workers.gathering:
                    # Just relocate the workers that are too far from the available resources
                    if not minerals_close and scv.is_carrying_minerals:
                        scv.return_resource()
                    elif not geysers_close and scv.is_carrying_vespene:
                        scv.return_resource()
                    else:
                        # Otherwise, move to the new mineral patches
                        scv.move(new_location)

    async def find_new_resource_location(self):
        # Sort expansions based on distance to current location and return the first one that is not taken
        unoccupied_expansions = [expansion for expansion in self.expansion_locations_list if
                                 not self.is_expansion_taken(expansion)]
        if unoccupied_expansions:
            return min(unoccupied_expansions, key=lambda expansion: self.start_location.distance_to(expansion))

        # If no unoccupied expansions are available, then return None
        return None

    def is_expansion_taken(self, expansion):
        return any(cc.position.is_same_as(expansion) for cc in self.townhalls)

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
        max_barracks = 4 if self.minutes_passed < 10 else 5
        max_factories = 2 if self.minutes_passed < 15 else 4
        max_starports = 2 if self.minutes_passed < 15 else 4
        max_armories = 1

        if self.structures(UnitTypeId.SUPPLYDEPOT).ready.exists:
            # Create production buildings based on requirements for your chosen army composition
            barracks_count = self.structures(UnitTypeId.BARRACKS).amount + self.already_pending(UnitTypeId.BARRACKS)
            factory_count = self.structures(UnitTypeId.FACTORY).amount + self.already_pending(UnitTypeId.FACTORY)
            starport_count = self.structures(UnitTypeId.STARPORT).amount + self.already_pending(UnitTypeId.STARPORT)
            armory_count = self.structures(UnitTypeId.ARMORY).amount + self.already_pending(UnitTypeId.ARMORY)

            # Requirements for building production structures
            need_more_barracks = self.can_afford(UnitTypeId.BARRACKS) and barracks_count < max_barracks
            need_more_factories = self.can_afford(UnitTypeId.FACTORY) and factory_count < max_factories
            need_more_starports = self.can_afford(UnitTypeId.STARPORT) and starport_count < max_starports

            # Build Armory after the first Factory
            need_armory = self.can_afford(UnitTypeId.ARMORY) and armory_count < max_armories and factory_count > 0

            # Logic to build Barracks, Factories, Starports, and an Armory
            if need_more_barracks:
                await self.build_building_near(UnitTypeId.BARRACKS, self.start_location.position)

            if need_more_factories and barracks_count > 0:  # Ensure we have a Barracks before building a Factory
                await self.build_building_near(UnitTypeId.FACTORY, self.start_location.position)

            if need_more_starports and factory_count > 0:  # Ensure we have a Factory before building a Starport
                await self.build_building_near(UnitTypeId.STARPORT, self.start_location.position)

            if need_armory:
                await self.build_building_near(UnitTypeId.ARMORY, self.start_location.position)

    # Produce combat units from available barracks
    async def build_offensive_force(self):
        # Dynamic unit targets based on the current game state
        marine_count_target = 16 if self.minutes_passed < 10 else 24
        marauder_count_target = 8 if self.minutes_passed < 10 else 16
        medivac_count_target = 2 if self.minutes_passed < 10 else 4
        banshee_count_target = 2 if self.minutes_passed < 10 else 8
        reaper_count_target = 4 if self.minutes_passed < 5 else 0
        siege_tank_count_target = 2 if self.minutes_passed < 15 else 8

        # Check if we have the required buildings before training units
        barracks_ready = self.structures(UnitTypeId.BARRACKS).ready.exists
        factory_ready = self.structures(UnitTypeId.FACTORY).ready.exists
        starport_ready = self.structures(UnitTypeId.STARPORT).ready.exists

        # Adjust unit production based on scouting information and current needs
        if barracks_ready:
            for rax in self.structures(UnitTypeId.BARRACKS).ready.idle:
                if self.can_afford(UnitTypeId.MARINE) and self.units(UnitTypeId.MARINE).amount + self.already_pending(
                        UnitTypeId.MARINE) < marine_count_target:
                    rax.train(UnitTypeId.MARINE)

                # Include a check to see if a Tech Lab is attached for Marauders and if we've hit our target count
                elif self.can_afford(UnitTypeId.MARAUDER) and rax.has_add_on and self.units(
                        UnitTypeId.MARAUDER).amount + self.already_pending(UnitTypeId.MARAUDER) < marauder_count_target:
                    rax.train(UnitTypeId.MARAUDER)

                # Reaper training prioritized early game for harassment
                if self.can_afford(UnitTypeId.REAPER) and self.units(UnitTypeId.REAPER).amount + self.already_pending(
                        UnitTypeId.REAPER) < reaper_count_target:
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
        # Check if we have an Engineering Bay for infantry upgrades
        if self.structures(UnitTypeId.ENGINEERINGBAY).ready.exists:
            await self.research_infantry_upgrades()

        # Check if we have a Barracks with a Tech Lab for infantry upgrades
        if self.structures(UnitTypeId.BARRACKSTECHLAB).ready.exists:
            await self.research_barracks_upgrades()

        # Check if we have an Armory for vehicle and ship upgrades
        if self.structures(UnitTypeId.ARMORY).ready.exists:
            await self.research_armory_upgrades()

    async def research_infantry_upgrades(self):
        engineering_bay = self.structures(UnitTypeId.ENGINEERINGBAY).ready.first

        # Research infantry weapons and armor upgrades
        if not self.already_pending_upgrade(UpgradeId.TERRANINFANTRYWEAPONSLEVEL1) and self.can_afford(
                UpgradeId.TERRANINFANTRYWEAPONSLEVEL1):
            engineering_bay.research(UpgradeId.TERRANINFANTRYWEAPONSLEVEL1)

        if not self.already_pending_upgrade(UpgradeId.TERRANINFANTRYARMORSLEVEL1) and self.can_afford(
                UpgradeId.TERRANINFANTRYARMORSLEVEL1):
            engineering_bay.research(UpgradeId.TERRANINFANTRYARMORSLEVEL1)

    async def research_barracks_upgrades(self):
        tech_lab = self.structures(UnitTypeId.BARRACKSTECHLAB).ready.first

        # Research Stimpack and Combat Shield
        if not self.already_pending_upgrade(UpgradeId.STIMPACK) and self.can_afford(UpgradeId.STIMPACK):
            tech_lab.research(UpgradeId.STIMPACK)

        if not self.already_pending_upgrade(UpgradeId.SHIELDWALL) and self.can_afford(UpgradeId.SHIELDWALL):
            tech_lab.research(UpgradeId.SHIELDWALL)

    async def research_armory_upgrades(self):
        armory = self.structures(UnitTypeId.ARMORY).ready.first

        # Research vehicle and ship plating and weapons upgrades
        if not self.already_pending_upgrade(UpgradeId.TERRANVEHICLEANDSHIPARMORSLEVEL1) and self.can_afford(
                UpgradeId.TERRANVEHICLEANDSHIPARMORSLEVEL1):
            armory.research(UpgradeId.TERRANVEHICLEANDSHIPARMORSLEVEL1)

        if not self.already_pending_upgrade(UpgradeId.TERRANVEHICLEWEAPONSLEVEL1) and self.can_afford(
                UpgradeId.TERRANVEHICLEWEAPONSLEVEL1):
            armory.research(UpgradeId.TERRANVEHICLEWEAPONSLEVEL1)

    async def research_upgrade(self, upgrade_id, structure, required_structure_type=None):
        # Check if the upgrade is not already being researched or completed, and if we can afford it
        if not self.already_pending_upgrade(upgrade_id) and self.can_afford(upgrade_id):
            # Check if a required structure type is needed before researching (e.g. Armory for higher levels)
            if required_structure_type:
                required_structure = self.structures(required_structure_type).ready
                if not required_structure.exists:
                    # Required structure not available, cannot research this upgrade yet
                    return
            # Issue the research order
            structure.research(upgrade_id)

    async def upgrade_structures(self):
        # Engineering Bay upgrades for structures
        if self.structures(UnitTypeId.ENGINEERINGBAY).ready.exists:
            eb = self.structures(UnitTypeId.ENGINEERINGBAY).ready.first
            await self.research_upgrade(UpgradeId.HISECAUTOTRACKING, eb)
            await self.research_upgrade(UpgradeId.TERRANBUILDINGARMOR, eb)

        # Command Center upgrades to Orbital Command or Planetary Fortress
        for cc in self.townhalls(UnitTypeId.COMMANDCENTER).idle:
            # If the required upgrades are finished or not necessary, consider upgrading to Orbital Command or
            # Planetary Fortress
            if self.can_afford(UnitTypeId.ORBITALCOMMAND) and not cc.has_add_on:
                cc(AbilityId.UPGRADETOORBITAL_ORBITALCOMMAND)

            if self.can_afford(UnitTypeId.PLANETARYFORTRESS) and not cc.has_add_on:
                cc(AbilityId.UPGRADETOPLANETARYFORTRESS_PLANETARYFORTRESS)

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
    async def build_building_near(self, building_type, position, max_distance=30):
        try:
            location = await self.find_placement(building_type, position, max_distance=max_distance)
            if location:
                await self.build(building_type, location)
                return True  # Successfully found a location and issued a build command
        except Exception as e:
            print(str(e))
        return False  # Failed to find a location/build the structure

    async def build_engineering_bay(self):
        # Check if you already have an ENGINEERINGBAY
        if not self.structures(UnitTypeId.ENGINEERINGBAY).exists:
            # Ensure you have enough resources before trying to build
            if self.can_afford(UnitTypeId.ENGINEERINGBAY):
                await self.build_building_near(UnitTypeId.ENGINEERINGBAY, self.start_location.position)

    #  defense strategy
    async def defend(self):
        for unit in self.units:
            if self.enemy_units.closer_than(15, unit.position).exists:
                defensive_squad = self.units.filter(
                    lambda unit: unit.type_id in {UnitTypeId.MARINE, UnitTypeId.MARAUDER, UnitTypeId.REAPER,
                                                  UnitTypeId.SIEGETANK, UnitTypeId.SIEGETANKSIEGED})
                await self.defend_location(unit, self.enemy_units, defensive_squad)
                return True

        for th in self.townhalls:
            enemies = self.enemy_units.closer_than(15, th.position)
            # Check if there are enemy units and if we have enough units to defend
            if enemies.exists:
                defensive_squad = self.units.filter(
                    lambda unit: unit.type_id in {UnitTypeId.MARINE, UnitTypeId.MARAUDER, UnitTypeId.REAPER,
                                                  UnitTypeId.SIEGETANK, UnitTypeId.SIEGETANKSIEGED})

                await self.defend_location(th, enemies, defensive_squad)
                return True
        return False

    # micro-management for army units
    async def manage_army_micro(self):
        for tank in self.units(UnitTypeId.SIEGETANK):
            await self.siege_tank_micro(tank)

        for tank in self.units(UnitTypeId.SIEGETANKSIEGED):
            await self.siege_tank_micro(tank)

    async def siege_tank_micro(self, tank):
        if self.enemy_units.in_attack_range_of(tank) or self.enemy_structures.in_attack_range_of(tank):
            tank(AbilityId.SIEGEMODE_SIEGEMODE)

        if not self.enemy_units.in_attack_range_of(tank) and not self.enemy_structures.in_attack_range_of(tank):
            tank(AbilityId.UNSIEGE_UNSIEGE)

    async def defend_location(self, location, enemies, defensive_squad):
        if defensive_squad.amount > 5:
            # Get Medivacs from the defensive squad
            medivacs = self.units(UnitTypeId.MEDIVAC)

            # Use the rest of the defensive squad to engage the enemy
            if enemies.exists:
                for unit in defensive_squad:
                    unit.attack(enemies.closest_to(location))

                # Medivacs should follow and heal the combat units
                for medivac in medivacs:
                    # Find the closest ground unit that the Medivac can follow and heal
                    if defensive_squad.exists:  # Make sure there are units to follow
                        closest_combat_unit = defensive_squad.closest_to(medivac)
                        medivac.move(closest_combat_unit)

    def choose_rally_point(self):
        if self.enemy_start_locations:
            rally_point = self.start_location.towards(self.enemy_start_locations[0], distance=20)
        else:
            rally_point = self.start_location.towards(self.game_info.map_center, distance=20)
        return rally_point

    async def regroup_at_rally_point(self):
        # Regroup idle military units at the rally point
        if self.rally_point:
            for unit in self.units.idle:
                if unit.type_id in {UnitTypeId.MARINE, UnitTypeId.MARAUDER, UnitTypeId.REAPER, UnitTypeId.SIEGETANK,
                                    UnitTypeId.MEDIVAC, UnitTypeId.SIEGETANKSIEGED}:
                    unit.move(self.rally_point)

    # Calculate elapsed game time minutes
    @property
    def minutes_passed(self):
        return self.state.game_loop / (22.4 * 60)


# Run the game
run_game(
    maps.get("sc2-ai-cup-2022"),
    [Bot(Race.Terran, StarCraftBot()), Computer(Race.Terran, Difficulty.Hard)],
    realtime=False,
)
