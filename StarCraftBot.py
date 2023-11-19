import math
import random

from sc2 import maps
from sc2.bot_ai import BotAI
from sc2.data import Race, Difficulty
from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId
from sc2.main import run_game
from sc2.player import Bot, Computer
from sc2.position import Point2


def defend_base(location, enemies, defensive_squad):
    if enemies.exists:
        # If the idle defensive squad is smaller than the minimum defense squad, get more units
        if defensive_squad.amount > 5:
            for unit in defensive_squad:
                unit.attack(enemies.closest_to(location))


def find_perimeter_position_for_bunker(center, min_distance):
    # Attempt to find the position of a Bunker at the perimeter of the base
    for _ in range(5):  # Try several times to get a suitable position
        # Generate a random angle
        angle = random.uniform(0, 2 * math.pi)
        # Create a point at the perimeter using polar coordinates
        position = Point2((math.cos(angle), math.sin(angle))) * min_distance + center

        if position:
            return position
    # No suitable location found
    return None


class StarCraftBot(BotAI):
    def __init__(self):
        super().__init__()

        self.last_expansion_attempt = -999
        self.EXPANSION_LIMIT = 3  # Max number of expansions
        self.MINERALS_FOR_EXPANSION = 200  # Amount of minerals to be saved for expansion
        self.EXPANSION_COOLDOWN = 150  # Cooldown (game steps) between expansions to avoid over-expanding

    async def on_step(self, iteration: int):
        if iteration % 50 == 0:
            await self.check_and_relocate_workers()

        # Send scout every 5 minutes
        if self.state.game_loop % (10 * 60 * 22.4) == 0:
            await self.send_scout()

        if self.minutes_passed < 1:
            await self.manage_economy()
        else:
            # Try to defend if under attack, otherwise proceed with normal strategy
            if not await self.defend():
                # Regular strategy execution
                await self.manage_economy()
                await self.manage_army()
                await self.attacking_strategy()

            await self.build_offensive_force()

        # Method to manage economic development such as building workers and expanding

    async def manage_economy(self):
        await self.distribute_workers()
        await self.build_workers()
        await self.manage_expansion()
        await self.build_supply_depots()
        await self.build_refinery()
        await self.build_engineering_bay()
        # await self.build_defensive_structures() not effective
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
                                          UnitTypeId.SIEGETANK})
        medivacs = self.units(UnitTypeId.MEDIVAC)

        # Check army size to see if it's time to attack
        attack_force_size = 42
        if army_units.amount >= attack_force_size:
            # Find a target
            target = self.find_target()
            for unit in army_units.idle:
                unit.attack(target)
            for medivac in medivacs.idle:
                # Follow the main army to provide healing
                medivac.move(army_units.closest_to(target))
        # Additional Medivac logic when no army units are left
        elif medivacs.exists:
            await self.retreat_medivacs(medivacs)

    async def retreat_medivacs(self, medivacs):
        # Find a safe location to retreat to, typically one of your own bases.
        safe_location = self.start_location  # Fallback to the start location

        # If there is a better safe location, like a base that is under less threat, use that instead.
        # This simple version just returns to the start location.
        for medivac in medivacs:
            medivac.move(safe_location)

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

    # Send out the initial scout worker at the start of the game
    async def send_scout(self):
        worker = self.workers.random
        for expansion in self.expansion_locations_list:
            worker.move(expansion)

    # SCV production across all command centers
    async def build_workers(self):
        early_game_scv_limit = 32
        late_game_scv_limit = 48

        if self.minutes_passed < 10:
            scv_limit = early_game_scv_limit
        else:
            scv_limit = late_game_scv_limit

        ideal_scv_per_cc = 16
        if self.workers.amount < min(ideal_scv_per_cc * self.townhalls.amount, scv_limit) and self.supply_left > 0:
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
        max_barracks = 3 if self.minutes_passed < 10 else 4
        max_factories = 2 if self.minutes_passed < 10 else 3
        max_starports = 2 if self.minutes_passed < 10 else 3
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

            # TODO: -- NOT WORKING
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
        # Logic to determine the number of each type of unit to have at different stages of the game
        marine_count_target = 24
        marauder_count_target = 8 if self.minutes_passed < 10 else 16
        medivac_count_target = 2 if self.minutes_passed < 10 else 4
        banshee_count_target = 2 if self.minutes_passed < 10 else 12
        reaper_count_target = 4 if self.minutes_passed < 5 else 0
        siege_tank_count_target = 1 if self.minutes_passed < 10 else 12

        # Check if we have the required buildings before training units
        barracks_ready = self.structures(UnitTypeId.BARRACKS).ready.exists
        factory_ready = self.structures(UnitTypeId.FACTORY).ready.exists
        starport_ready = self.structures(UnitTypeId.STARPORT).ready.exists

        # Training logic for each unit type based on available buildings and resources
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
        # Check for a ready Engineering Bay for infantry upgrades
        if self.structures(UnitTypeId.ENGINEERINGBAY).ready.exists:
            eb = self.structures(UnitTypeId.ENGINEERINGBAY).ready.first

            # Trigger Infantry Weapon and Armor upgrades sequentially if we have the resources
            await self.research_upgrade(UpgradeId.TERRANINFANTRYWEAPONSLEVEL1, eb)
            await self.research_upgrade(UpgradeId.TERRANINFANTRYWEAPONSLEVEL2, eb,
                                        required_structure_type=UnitTypeId.ARMORY)
            await self.research_upgrade(UpgradeId.TERRANINFANTRYWEAPONSLEVEL3, eb,
                                        required_structure_type=UnitTypeId.ARMORY)
            await self.research_upgrade(UpgradeId.TERRANINFANTRYARMORSLEVEL1, eb)
            await self.research_upgrade(UpgradeId.TERRANINFANTRYARMORSLEVEL2, eb,
                                        required_structure_type=UnitTypeId.ARMORY)
            await self.research_upgrade(UpgradeId.TERRANINFANTRYARMORSLEVEL3, eb,
                                        required_structure_type=UnitTypeId.ARMORY)

        # Check for a ready Armory for vehicle and ship upgrades
        if self.structures(UnitTypeId.ARMORY).ready.exists:
            armory = self.structures(UnitTypeId.ARMORY).ready.first

            # Trigger Vehicle and Ship Weapon and Armor upgrades sequentially if we have the resources
            await self.research_upgrade(UpgradeId.TERRANVEHICLEWEAPONSLEVEL1, armory)
            await self.research_upgrade(UpgradeId.TERRANVEHICLEWEAPONSLEVEL2, armory)
            await self.research_upgrade(UpgradeId.TERRANVEHICLEWEAPONSLEVEL3, armory)
            await self.research_upgrade(UpgradeId.TERRANSHIPWEAPONSLEVEL1, armory)
            await self.research_upgrade(UpgradeId.TERRANSHIPWEAPONSLEVEL2, armory)
            await self.research_upgrade(UpgradeId.TERRANSHIPWEAPONSLEVEL3, armory)
            await self.research_upgrade(UpgradeId.TERRANVEHICLEANDSHIPARMORSLEVEL1, armory)
            await self.research_upgrade(UpgradeId.TERRANVEHICLEANDSHIPARMORSLEVEL2, armory)
            await self.research_upgrade(UpgradeId.TERRANVEHICLEANDSHIPARMORSLEVEL3, armory)

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
    async def build_building_near(self, building_type, position, max_distance=25):
        # Note that try...except blocks are used to handle the situation where the bot may be unable to find a
        # valid build location (e.g. all locations are blocked or currently occupied).
        try:
            location = await self.find_placement(building_type, position, max_distance=max_distance)
            if location:
                await self.build(building_type, location)
                return True  # Successfully found a location and issued a build command
        except Exception as e:
            print(str(e))  # For debugging purposes, remove or handle this print as desired in production
        return False  # Failed to find a location/build the structure

    async def build_engineering_bay(self):
        # Check if you already have an ENGINEERINGBAY
        if not self.structures(UnitTypeId.ENGINEERINGBAY).exists:
            # Ensure you have enough resources before trying to build
            if self.can_afford(UnitTypeId.ENGINEERINGBAY):
                await self.build_building_near(UnitTypeId.ENGINEERINGBAY, self.start_location.position)

    async def build_defensive_structures(self):
        for cc in self.townhalls.ready:
            await self.build_bunkers(cc)

    async def build_bunkers(self, cc):
        # Desired number of Bunkers around each base
        desired_bunker_count = 2
        edge_distance = 15

        # Check if we can afford a Bunker and have less than the desired count
        if self.can_afford(UnitTypeId.BUNKER) and self.structures(UnitTypeId.BUNKER).closer_than(
                edge_distance, cc).amount < desired_bunker_count:
            # Find placement position around the base outside the mineral line
            position = find_perimeter_position_for_bunker(cc.position, edge_distance)
            if position:
                # If a valid position is found, try to build a Bunker there
                await self.build_building_near(UnitTypeId.BUNKER, position, max_distance=edge_distance)

    async def defend(self):
        for th in self.townhalls:
            enemies = self.enemy_units.closer_than(15, th.position)
            if enemies.exists:
                defensive_squad = self.units.idle
                defend_base(th, enemies, defensive_squad)
                return True
        return False

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
