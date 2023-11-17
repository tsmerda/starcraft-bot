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
        await self.attack()

        # Distribute workers to ensure optimal resource collection
        await self.distribute_workers()

        # Build workers from every idle command center
        await self.build_workers()

        # Build supply depots near the first command center
        await self.build_supply_depots()

        # Expand to a new resource location if we can afford and have less than 3 command centers
        await self.expand()

        await self.build_refinery()

        await self.offensive_force_buildings()

        await self.build_techlab()

        await self.build_advanced_units()

        await self.build_offensive_force()

        # Vylepšení jednotek
        # await self.upgrade_units()

        # Výroba pokročilých jednotek

        # await self.upgrade_at_techlab()

        # Omezení produkce mariňáků

    async def build_workers(self):
        early_game_scv_limit = 22  # Limit pro ranou fázi hry
        mid_game_scv_limit = 40  # Limit pro střední fázi hry
        late_game_scv_limit = 60  # Limit pro pozdní fázi hry

        # Určení aktuální fáze hry
        if self.minutes_passed < 5:  # Příklad pro ranou fázi
            scv_limit = early_game_scv_limit
        elif self.minutes_passed < 10:  # Příklad pro střední fázi
            scv_limit = mid_game_scv_limit
        else:  # Pozdní fáze
            scv_limit = late_game_scv_limit

        ideal_scv_per_cc = 16  # Ideální počet SCV na Command Center
        if (
            self.workers.amount
            < min(ideal_scv_per_cc * self.townhalls.amount, scv_limit)
            and self.supply_left > 0
        ):
            for cc in self.townhalls.ready.idle:
                if self.can_afford(UnitTypeId.SCV):
                    cc.train(UnitTypeId.SCV)

    async def build_supply_depots(self):
        # If we are running out of supply, and we are not already building a supply depot...
        if self.supply_left < 8 and not self.already_pending(UnitTypeId.SUPPLYDEPOT):
            ccs = self.townhalls.ready
            if ccs.exists and self.can_afford(UnitTypeId.SUPPLYDEPOT):
                # Vybíráme nejlepší místo pro stavbu
                location = self.main_base_ramp.top_center.towards(
                    self.game_info.map_center, 5
                )
                await self.build(UnitTypeId.SUPPLYDEPOT, near=location)

    async def expand(self):
        # If we have less than 2 command centers and can afford to build one...
        if self.townhalls.amount < 3 and self.can_afford(UnitTypeId.COMMANDCENTER):
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
        max_factories = 2  # Stanovení maximálního počtu Factory

        # Sloučení logiky stavby vojenských budov
        if self.structures(UnitTypeId.SUPPLYDEPOT).ready.exists:
            depot = self.structures(UnitTypeId.SUPPLYDEPOT).ready.random

            if not self.structures(UnitTypeId.BARRACKS).exists and self.can_afford(
                UnitTypeId.BARRACKS
            ):
                await self.build(UnitTypeId.BARRACKS, near=depot)

            if self.structures(UnitTypeId.BARRACKS).ready.exists:
                if self.structures(UnitTypeId.FACTORY).amount < max_factories:
                    if not self.structures(
                        UnitTypeId.FACTORY
                    ).exists and self.can_afford(UnitTypeId.FACTORY):
                        await self.build(UnitTypeId.FACTORY, near=depot)

                if not self.structures(UnitTypeId.ARMORY).exists and self.can_afford(
                    UnitTypeId.ARMORY
                ):
                    await self.build(UnitTypeId.ARMORY, near=depot)

                if not self.structures(UnitTypeId.STARPORT).exists and self.can_afford(
                    UnitTypeId.STARPORT
                ):
                    await self.build(UnitTypeId.STARPORT, near=depot)

    async def build_offensive_force(self):
        marine_limit = 6
        reaper_limit = 6
        marauder_limit = 14

        if (
            self.units(UnitTypeId.MARINE).amount < marine_limit
            or self.units(UnitTypeId.REAPER).amount < reaper_limit
            or self.units(UnitTypeId.MARAUDER).amount < marauder_limit
        ):
            for rax in self.structures(UnitTypeId.BARRACKS).ready.idle:
                if rax.is_idle and self.supply_left > 0:
                    if self.units(
                        UnitTypeId.MARAUDER
                    ).amount < reaper_limit and self.can_afford(UnitTypeId.MARAUDER):
                        rax.train(UnitTypeId.MARAUDER)
                    elif self.units(
                        UnitTypeId.MARINE
                    ).amount < marine_limit and self.can_afford(UnitTypeId.MARINE):
                        rax.train(UnitTypeId.MARINE)
                    elif self.units(
                        UnitTypeId.REAPER
                    ).amount < reaper_limit and self.can_afford(UnitTypeId.REAPER):
                        rax.train(UnitTypeId.REAPER)

    def find_target(self):
        if self.enemy_units:
            return random.choice(self.enemy_units)
        elif self.enemy_structures:
            return random.choice(self.enemy_structures)
        else:
            return self.enemy_start_locations[0]

    async def attack(self):
        total_offensive_units = (
            self.units(UnitTypeId.MARINE).amount
            + self.units(UnitTypeId.REAPER).amount
            + self.units(UnitTypeId.MARAUDER).amount
        )

        if total_offensive_units > 12:
            target = self.find_target()
            for unit in (
                self.units(UnitTypeId.MARINE)
                | self.units(UnitTypeId.REAPER)
                | self.units(UnitTypeId.MARAUDER)
            ):
                if unit.is_idle:
                    unit.attack(target)

        # async def upgrade_units(self):
        #     if self.structures(UnitTypeId.ENGINEERINGBAY).ready.exists:
        #         eng_bay = self.structures(UnitTypeId.ENGINEERINGBAY).ready.first
        #         if not eng_bay.has_researched(
        #             UpgradeId.TERRANINFANTRYWEAPONSLEVEL1
        #         ) and self.can_afford(UpgradeId.TERRANINFANTRYWEAPONSLEVEL1):
        #             eng_bay.research(UpgradeId.TERRANINFANTRYWEAPONSLEVEL1)
        #         # Podobně pro další vylepšení

        #     if self.structures(UnitTypeId.ARMORY).ready.exists:
        #         armory = self.structures(UnitTypeId.ARMORY).ready.first
        #         if not armory.has_researched(
        #             UpgradeId.TERRANVEHICLEANDSHIPPLATINGLEVEL1
        #         ) and self.can_afford(UpgradeId.TERRANVEHICLEANDSHIPPLATINGLEVEL1):
        #             armory.research(UpgradeId.TERRANVEHICLEANDSHIPPLATINGLEVEL1)
        #         # Další vylepšení

    async def build_techlab(self):
        # Získání počtu Command Centers
        num_ccs = self.townhalls.ready.amount

        # Získání počtu Barracks s Tech Labem
        num_techlabs = self.structures(UnitTypeId.BARRACKSTECHLAB).ready.amount

        # Kontrola, zda máme méně Tech Labs než Command Centers
        if num_techlabs < num_ccs:
            for rax in self.structures(UnitTypeId.BARRACKS).ready.idle:
                if not rax.has_add_on and self.can_afford(UnitTypeId.BARRACKSTECHLAB):
                    rax.build(UnitTypeId.BARRACKSTECHLAB)

    # async def upgrade_at_techlab(self):
    #     # Procházet všechny Tech Labs připojené k Barracks
    #     for lab in self.structures(UnitTypeId.BARRACKSTECHLAB).ready:
    #         # Kontrola, zda je Tech Lab nečinný a zda máme dostatek zdrojů pro vylepšení
    #         if lab.is_idle:
    #             # Příklad vylepšení: Stimpack
    #             if self.can_afford(
    #                 AbilityId.RESEARCH_STIMPACK
    #             ) and not self.already_pending_upgrade(UpgradeId.STIMPACK):
    #                 lab.research(AbilityId.RESEARCH_STIMPACK)
    # Další vylepšení mohou být přidána zde

    async def build_advanced_units(self):
        if self.structures(UnitTypeId.STARPORT).ready.exists:
            for starport in self.structures(UnitTypeId.STARPORT).ready.idle:
                if self.can_afford(UnitTypeId.BANSHEE):
                    starport.train(UnitTypeId.BANSHEE)

        if self.structures(UnitTypeId.FACTORY).ready.exists:
            for factory in self.structures(UnitTypeId.FACTORY).ready.idle:
                if self.can_afford(UnitTypeId.SIEGETANK):
                    factory.train(UnitTypeId.SIEGETANK)

    @property
    def minutes_passed(self):
        return self.state.game_loop / (22.4 * 60)


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
