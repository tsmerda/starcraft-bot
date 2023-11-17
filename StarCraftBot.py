import random

from sc2 import maps
from sc2.bot_ai import BotAI
from sc2.data import Race, Difficulty
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.upgrade_id import UpgradeId
from sc2.main import run_game
from sc2.player import Bot, Computer


class WorkerRushBot(BotAI):
    def __init__(self):
        super().__init__()
        self.last_expansion_attempt = -999

    async def on_step(self, iteration: int):
        if iteration == 0:
            await self.send_initial_scout()

        defending = await self.defend()

        if not defending:
            await self.attack()
            await self.distribute_workers()
            await self.build_workers()
            await self.build_supply_depots()
            await self.smart_expand()
            await self.build_refinery()
            await self.offensive_force_buildings()
            await self.build_techlab()
            await self.build_advanced_units()
            await self.build_offensive_force()
            await self.build_engineering_bay()
            await self.upgrade_units()
            await self.build_defensive_structures()

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

    async def build_supply_depots(self):
        if self.supply_left < 5 and not self.already_pending(UnitTypeId.SUPPLYDEPOT):
            ccs = self.townhalls.ready
            if ccs.exists and self.can_afford(UnitTypeId.SUPPLYDEPOT):
                location = await self.find_placement(
                    UnitTypeId.SUPPLYDEPOT, self.main_base_ramp.barracks_correct_placement,
                    max_distance=20, random_alternative=False, placement_step=2
                )
                if location:
                    await self.build(UnitTypeId.SUPPLYDEPOT, near=location)

    async def smart_expand(self):
        if self.time - self.last_expansion_attempt > 10:
            if self.townhalls.amount < 5 and self.can_afford(UnitTypeId.COMMANDCENTER):
                location = await self.get_next_expansion()
                if location:
                    enemies_nearby = self.enemy_units.closer_than(20, location)
                    if not enemies_nearby.exists:
                        await self.expand_now()
                        self.last_expansion_attempt = self.time
                    else:
                        self.last_expansion_attempt = self.time

    async def build_refinery(self):
        for cc in self.townhalls.ready:
            vaspenes = self.vespene_geyser.closer_than(25.0, cc)
            for vaspene in vaspenes:
                if not self.can_afford(UnitTypeId.REFINERY) or self.already_pending(UnitTypeId.REFINERY):
                    break
                worker = self.select_build_worker(vaspene.position)
                if worker is None or self.units(UnitTypeId.REFINERY).closer_than(1.0, vaspene).exists:
                    continue
                worker.build(UnitTypeId.REFINERY, vaspene)

    async def offensive_force_buildings(self):
        max_factories = 2

        if self.structures(UnitTypeId.SUPPLYDEPOT).ready.exists:
            depot = self.structures(UnitTypeId.SUPPLYDEPOT).ready.random

            if not self.structures(UnitTypeId.BARRACKS).exists and self.can_afford(UnitTypeId.BARRACKS):
                await self.build(UnitTypeId.BARRACKS, near=depot)

            if self.structures(UnitTypeId.BARRACKS).ready.exists:
                if self.structures(UnitTypeId.FACTORY).amount < max_factories and not self.structures(
                        UnitTypeId.FACTORY).exists and self.can_afford(UnitTypeId.FACTORY):
                    await self.build(UnitTypeId.FACTORY, near=depot)

                if not self.structures(UnitTypeId.ARMORY).exists and self.can_afford(UnitTypeId.ARMORY):
                    await self.build(UnitTypeId.ARMORY, near=depot)

                if not self.structures(UnitTypeId.STARPORT).exists and self.can_afford(UnitTypeId.STARPORT):
                    await self.build(UnitTypeId.STARPORT, near=depot)

    async def build_offensive_force(self):
        # Improved offensive force method to produce a more balanced army composition
        if self.supply_left > 0 and self.structures(UnitTypeId.BARRACKS).ready.exists:
            # if early game, prioritize Marines and Reapers for harassment
            if self.minutes_passed < 5:
                # Create Reapers if we have less than 4
                if self.units(UnitTypeId.REAPER).amount < 4 and self.can_afford(UnitTypeId.REAPER):
                    self.train(UnitTypeId.REAPER, 1)
                # Fill the rest with Marines
                elif self.can_afford(UnitTypeId.MARINE):
                    self.train(UnitTypeId.MARINE, 5)
            else:
                # Mid to late game, prioritize a mix of Marines, Marauders, and Medivacs
                if self.units(UnitTypeId.MARAUDER).amount < 8 and self.can_afford(UnitTypeId.MARAUDER):
                    self.train(UnitTypeId.MARAUDER, 1)
                elif self.can_afford(UnitTypeId.MARINE):
                    self.train(UnitTypeId.MARINE, 5)
                elif self.units(UnitTypeId.MEDIVAC).amount < 3 and self.can_afford(UnitTypeId.MEDIVAC):
                    self.train(UnitTypeId.MEDIVAC, 1)

    def find_target(self):
        if self.enemy_units:
            return random.choice(self.enemy_units)
        elif self.enemy_structures:
            return random.choice(self.enemy_structures)
        else:
            return self.enemy_start_locations[0]

    async def attack(self):
        attack_force_size = 24
        offensive_units = {UnitTypeId.MARINE, UnitTypeId.REAPER, UnitTypeId.MARAUDER}
        total_offensive_units = sum(self.units(unit_type).amount for unit_type in offensive_units)

        if total_offensive_units >= attack_force_size:
            target = self.find_target()
            for unit_type in offensive_units:
                for unit in self.units(unit_type).idle:
                    unit.attack(target)

    async def upgrade_units(self):
        if self.structures(UnitTypeId.ENGINEERINGBAY).ready.exists:
            if self.units(UnitTypeId.MARINE).amount > self.units(UnitTypeId.MARAUDER).amount:
                if self.can_afford(UpgradeId.TERRANINFANTRYWEAPONSLEVEL1) and not self.already_pending_upgrade(
                        UpgradeId.TERRANINFANTRYWEAPONSLEVEL1):
                    self.structures(UnitTypeId.ENGINEERINGBAY).ready.first.research(
                        UpgradeId.TERRANINFANTRYWEAPONSLEVEL1)
            else:
                if self.can_afford(UpgradeId.TERRANINFANTRYARMORSLEVEL1) and not self.already_pending_upgrade(
                        UpgradeId.TERRANINFANTRYARMORSLEVEL1):
                    self.structures(UnitTypeId.ENGINEERINGBAY).ready.first.research(
                        UpgradeId.TERRANINFANTRYARMORSLEVEL1)

    async def build_techlab(self):
        num_ccs = self.townhalls.ready.amount
        num_techlabs = self.structures(UnitTypeId.BARRACKSTECHLAB).ready.amount

        if num_techlabs < num_ccs:
            for rax in self.structures(UnitTypeId.BARRACKS).ready.idle:
                if not rax.has_add_on and self.can_afford(UnitTypeId.BARRACKSTECHLAB):
                    rax.build(UnitTypeId.BARRACKSTECHLAB)

    async def build_advanced_units(self):
        if self.structures(UnitTypeId.STARPORT).ready.exists:
            for starport in self.structures(UnitTypeId.STARPORT).ready.idle:
                if self.can_afford(UnitTypeId.BANSHEE):
                    starport.train(UnitTypeId.BANSHEE)

        if self.structures(UnitTypeId.FACTORY).ready.exists:
            for factory in self.structures(UnitTypeId.FACTORY).ready.idle:
                if self.can_afford(UnitTypeId.SIEGETANK):
                    factory.train(UnitTypeId.SIEGETANK)

    async def defend(self):
        for th in self.structures:
            if self.enemy_units.closer_than(20, th.position):
                await self.defend_base(th)
                return True
        return False

    async def defend_base(self, location):
        # Find the enemy units attacking our location
        enemies = self.enemy_units.closer_than(20, location.position)
        # If there are enemies, defend against them
        if enemies.exists:
            # Call all available military units to defend against the enemies
            for unit in self.units.idle:
                # Make each idle military unit attack the closest enemy unit
                unit.attack(enemies.closest_to(location))
            # Train additional units if needed
            for rax in self.structures(UnitTypeId.BARRACKS).ready.idle:
                if self.can_afford(UnitTypeId.MARINE):
                    rax.train(UnitTypeId.MARINE)

    async def build_engineering_bay(self):
        # Check if you already have an ENGINEERINGBAY
        if not self.structures(UnitTypeId.ENGINEERINGBAY).exists:
            # Ensure you have enough resources before trying to build
            if self.can_afford(UnitTypeId.ENGINEERINGBAY):
                # Pick the location near a Command Center or another suitable place
                location = await self.find_placement(UnitTypeId.ENGINEERINGBAY,
                                                     near=self.start_location.towards(self.game_info.map_center, 5))
                if location:
                    # Use a worker to build the ENGINEERINGBAY
                    worker = self.select_build_worker(location)
                    if worker:
                        worker.build(UnitTypeId.ENGINEERINGBAY, location)

    async def build_defensive_structures(self):
        # Ensure you have an Engineering Bay before building Missile Turrets
        if self.structures(UnitTypeId.ENGINEERINGBAY).ready.exists:
            await self.build_missile_turrets()

        # Build Bunkers at key defense positions
        await self.build_bunkers()

    async def build_missile_turrets(self):
        # Build Missile Turrets near mineral lines and important structures
        for cc in self.townhalls.ready:
            # Check if there are enough Missile Turrets around
            if self.structures(UnitTypeId.MISSILETURRET).closer_than(10, cc).amount < 2 and self.can_afford(
                    UnitTypeId.MISSILETURRET):
                # Find a proper location to build a turret
                location = await self.find_placement(UnitTypeId.MISSILETURRET,
                                                     cc.position.towards(self.game_info.map_center, 10))
                if location:
                    await self.build(UnitTypeId.MISSILETURRET, near=location)

    async def build_bunkers(self):
        limit = 5
        bunkers = self.structures(UnitTypeId.BUNKER)
        # Only continue if we have less than the desired number of Bunkers
        if bunkers.amount < limit:
            # Only build Bunkers if we have a Barracks and can afford it
            if self.structures(UnitTypeId.BARRACKS).ready.exists and self.can_afford(UnitTypeId.BUNKER):
                # Try to build a Bunker near the first Barracks
                target_barracks = self.structures(UnitTypeId.BARRACKS).ready.first
                location = await self.find_placement(UnitTypeId.BUNKER,
                                                     near=target_barracks.position.towards(self.game_info.map_center,
                                                                                           5))
                if location:
                    await self.build(UnitTypeId.BUNKER, near=location)

    @property
    def minutes_passed(self):
        return self.state.game_loop / (22.4 * 60)

    async def send_initial_scout(self):
        # Sends out the initial scout worker to enemy base
        worker = self.workers.random
        self.do(worker.move(self.enemy_start_locations[0]))


run_game(
    maps.get("sc2-ai-cup-2022"),
    [
        Bot(Race.Terran, WorkerRushBot()),
        Computer(Race.Terran, Difficulty.Easy),
    ],
    realtime=False,
)
