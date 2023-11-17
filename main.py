from sc2 import maps
from sc2.ids.unit_typeid import UnitTypeId
from sc2.player import Bot, Computer
from sc2.main import run_game
from sc2.data import Race, Difficulty
from sc2.bot_ai import BotAI
import random


class WorkerRushBot(BotAI):
    async def on_step(self, iteration: int):
        # This function is called at every game step (roughly every 0.2 seconds)

        # Print some useful information
        # print(f"Step: {iteration}, Workers: {self.workers.amount}, Idle workers: {self.workers.idle.amount},",
        #       f"Minerals: {self.minerals}, Gas: {self.vespene}, "
        #       f"Supply Depots: {self.structures(UnitTypeId.SUPPLYDEPOT).amount},",
        #       f"Command Centers: {self.structures(UnitTypeId.COMMANDCENTER).amount}",
        #       f"Barracks: {self.structures(UnitTypeId.BARRACKS).amount}, Supply: {self.supply_used}/{self.supply_cap}")

        # Call the attack method only under certain conditions
        if self.units(UnitTypeId.MARINE).amount > 3:
            await self.attack()

        # Distribute workers to ensure optimal resource collection
        await self.distribute_workers()

        # Build workers from every idle command center
        await self.build_workers()

        # Build supply depots near the first command center
        await self.build_supply_depots()

        # Expand to a new resource location if we can afford and have less than 2 command centers
        await self.expand()

        await self.build_refinery()

        await self.offensive_force_buildings()

        await self.build_offensive_force()

    async def build_workers(self):
        # For every command center in our control...
        for cc in self.townhalls.ready:
            # If the command center is idle, and we can afford a worker...
            if cc.is_idle and self.can_afford(UnitTypeId.SCV):
                # Train a worker
                cc.train(UnitTypeId.SCV)

    async def build_supply_depots(self):
        # If we are running out of supply, and we are not already building a supply depot...
        if self.supply_left < 5 and not self.already_pending(UnitTypeId.SUPPLYDEPOT):
            # If we have a command center and can afford a supply depot...
            ccs = self.townhalls.ready
            if ccs.exists and self.can_afford(UnitTypeId.SUPPLYDEPOT):
                # Build a supply depot near the first command center
                await self.build(UnitTypeId.SUPPLYDEPOT, near=ccs.first)

    async def expand(self):
        # If we have less than 2 command centers and can afford to build one...
        if self.townhalls.amount < 2 and self.can_afford(UnitTypeId.COMMANDCENTER):
            # Get the location of the next expansion
            location = await self.get_next_expansion()
            # If there is a location to expand to...
            if location:
                # Expand to a new resource location
                await self.expand_now()

    async def build_refinery(self):
        # Collect gas from refineries
        for cc in self.townhalls.ready:
            # Access vespene geysers within a certain distance of our command center
            vaspenes = self.vespene_geyser.closer_than(25.0, cc)
            for vaspene in vaspenes:
                # Check if we can afford a refinery, and if there's no worker on the way to build one
                if not self.can_afford(UnitTypeId.REFINERY) or self.already_pending(
                    UnitTypeId.REFINERY
                ):
                    break
                worker = self.select_build_worker(vaspene.position)
                if (
                    worker is None
                    or self.units(UnitTypeId.REFINERY).closer_than(1.0, vaspene).exists
                ):
                    continue
                # Command the worker to build a refinery
                worker.build(UnitTypeId.REFINERY, vaspene)

    async def offensive_force_buildings(self):
        if self.structures(UnitTypeId.SUPPLYDEPOT).ready.exists:
            depot = self.structures(UnitTypeId.SUPPLYDEPOT).ready.random
            if not self.structures(UnitTypeId.BARRACKS).exists:
                # Build a Barracks if we can afford it and none are already pending
                if self.can_afford(UnitTypeId.BARRACKS) and not self.already_pending(
                    UnitTypeId.BARRACKS
                ):
                    await self.build(UnitTypeId.BARRACKS, near=depot)
            else:
                if not self.structures(UnitTypeId.FACTORY).exists:
                    # Build a Factory if there is at least one Barracks, and we can afford it, and none are already
                    # pending
                    if self.can_afford(UnitTypeId.FACTORY) and not self.already_pending(
                        UnitTypeId.FACTORY
                    ):
                        await self.build(UnitTypeId.FACTORY, near=depot)

    async def build_offensive_force(self):
        for rax in self.structures(UnitTypeId.BARRACKS).ready:
            # Check if the Barracks has no orders (is idle)
            if (
                rax.is_idle
                and self.can_afford(UnitTypeId.MARINE)
                and self.supply_left > 0
            ):
                rax.train(UnitTypeId.MARINE)

    def find_target(self):
        if self.enemy_units:
            return random.choice(self.enemy_units)
        elif self.enemy_structures:
            return random.choice(self.enemy_structures)
        else:
            return self.enemy_start_locations[0]

    async def attack(self):
        if self.units(UnitTypeId.MARINE).amount > 15:
            target = self.find_target()
        else:
            target = (
                random.choice(self.enemy_units)
                if self.enemy_units
                else self.enemy_start_locations[0]
            )

        for marine in self.units(UnitTypeId.MARINE).idle:
            marine.attack(target)


run_game(
    maps.get("sc2-ai-cup-2022"),
    [
        Bot(Race.Terran, WorkerRushBot()),  # Bot plays as Terran
        Computer(
            Race.Terran, Difficulty.Easy
        ),  # Computer opponent plays as Terran with "easy" difficulty
    ],
    realtime=False,
)  # If set to True, the bot is limited in how long each step can take to process. False makes
# the game run as quickly as possible
