from tablereader import TableObject, set_global_table_filename
from utils import (read_multi, write_multi, classproperty, mutate_normal,
                   hexstring, utilrandom as random)
from shutil import copyfile
from os import path, remove
from sys import argv
from time import time


try:
    from sys import _MEIPASS
    tblpath = path.join(_MEIPASS, "tables")
except ImportError:
    tblpath = "tables"

spell_level_file = path.join(tblpath, "spell_level_table.txt")

g_learns = None
g_shops = None
RANDOMIZE = True


class UnknownObject(TableObject):
    pass


class InitialObject(TableObject):
    def __repr__(self):
        return "%x %x" % (self.addr, self.value)

    @property
    def is_learned_spell(self):
        return 0x5400 <= self.addr <= 0x5540

    @property
    def spell(self):
        if not self.is_learned_spell:
            return None
        return SpellObject.get(self.value)

    @property
    def char(self):
        if not self.is_learned_spell:
            return None
        char_id = (self.addr >> 5 & 0xf) - 1
        return CharacterObject.get(char_id)

    @property
    def catalogue_index(self):
        return self.addr, self.index

    def set_char(self, char_id):
        if not self.spell:
            raise Exception("Not an initially learned spell.")

        if not isinstance(char_id, int):
            char_id = char_id.index
        char_id += 1
        self.addr = self.addr & 0xFE1F
        self.addr |= (char_id << 5)

    def set_slot(self, index):
        assert index == index & 0x1f
        self.addr = (self.addr >> 5) << 5
        self.addr |= index


class SpellObject(TableObject):
    rankings = {}

    @property
    def rank(self):
        if self.rankings:
            return self.rankings[self]
        f = open(spell_level_file)
        for line in f:
            line = line.strip()
            if not line or line[0] == "#":
                continue
            while "  " in line:
                line = line.replace("  ", " ")
            index, level, _ = line.split(' ', 2)
            index, level = int(index, 0x10), int(level)
            rank = level
            so = SpellObject.get(index)
            self.rankings[so] = rank
        f.close()
        for so in SpellObject.every:
            assert so in self.rankings
        return self.rank


class CharacterObject(TableObject):
    stattrs = ["strength", "stamina", "agility", "wisdom", "luck",
               "max_hp", "max_ap"]

    def __repr__(self):
        if self.index > 8:
            return ""
        s = self.display_name + "\n"
        levelup = LevelUpObject.get(self.index)
        levels = [10, 20, 30, 50]
        if self.level not in levels:
            levels = [self.level] + levels
        for level in levels:
            if level < self.level:
                continue
            s2 = ("lv{0:2} hp:{6:3} ap:{7:3} str:{1:3} sta:{2:3} agi:{3:3} "
                  "wis:{4:3} luc:{5:3}")
            values = [levelup.value_at_level(attr, level) -
                      levelup.value_at_level(attr, self.level) +
                      getattr(self, attr) for attr in self.stattrs]
            values = [level] + values
            s2 = s2.format(*values)
            s += s2 + "\n"
        spellup = LearnObject.get(self.index)
        for level, spell in spellup.pairs:
            s += "lv{0:2} {1}\n".format(level, spell.display_name)
        return s.strip()

    def set_initial_equips(self):
        if self.index > 8:
            return
        elif self.index == 8:
            index = 7 - 4
        else:
            index = 7 - self.index
        mask = 1 << index
        candidates = [i for i in ItemObject.ranked if i.equippable & mask]
        self.weapon = [i for i in candidates if i.is_weapon][:2][-1].index
        self.shield = [i for i in candidates if i.is_shield][:2][-1].index
        self.helmet = [i for i in candidates if i.is_helmet][:2][-1].index
        self.armor = [i for i in candidates if i.is_armor][:2][-1].index

    def set_initial_stats(self):
        if self.index > 8:
            return
        self.level = mutate_normal(self.level, minimum=1, maximum=99)
        if self.index == 8:
            for attr in self.stattrs:
                value = getattr(self, attr)
                value = random.randint(1, value)
                setattr(self, attr, value)
            return

        self.guts = mutate_normal(self.guts, minimum=1)
        levelup = LevelUpObject.get(self.index)
        for attr in self.stattrs:
            value = levelup.value_at_level(attr, self.level)
            fifty = levelup.value_at_level(attr, 50)
            value += mutate_normal(fifty/5.0, minimum=1)
            value = min(value, 0xFF)
            setattr(self, attr, value)


class ItemObject(TableObject):
    equip_dict = {}
    suffix_dict = {
        None: ["BR", "BT", "SF"],
        0x05: ["DR"], 0x8a: ["SD"], 0x8b: ["DR"], 0x8c: ["RP"], 0x8d: [],
        0x8e: ["BW"], 0x8f: ["KN"], 0x90: ["ST"], 0x91: ["RG"], 0x92: ["WP"],
        0x93: ["HT", "Mask"], 0x94: ["AR", "RB", "ML", "CL"], 0x95: ["CL"],
        0x96: ["SH", "GL"], 0x97: ["DR"],
        }
    itemtypes = {
        "weapon": [0x05, 0x8a, 0x8b, 0x8c, 0x8e, 0x8f, 0x90, 0x91, 0x92, 0x97],
        "armor": [0x94, 0x95], "helmet": [0x93], "shield": [0x96],
        "accessory": [None],
        }
    newnames = []
    suffixes = sorted(set([sx for sxlist in suffix_dict.values()
                           for sx in sxlist]))
    for sx in suffixes:
        assert sx not in suffix_dict
        suffix_dict[sx] = sorted([key for key, vals in suffix_dict.items()
                                  if sx in vals])

    @property
    def suffix(self):
        for sx in self.suffixes:
            if self.display_name.endswith(sx):
                return sx

    @property
    def is_equippable(self):
        return any([getattr(self, "is_%s" % attr) for attr in
                    ["dragon", "weapon", "accessory", "armor",
                     "shield", "helmet"]])

    @property
    def is_dragon(self):
        return self.itemtype == 0x8d

    @property
    def is_weapon(self):
        if self.is_dragon:
            return self.index == 0x7b
        return self.itemtype in self.itemtypes["weapon"]

    @property
    def is_accessory(self):
        return 0x3f <= self.index <= 0x50

    @property
    def is_armor(self):
        if self.is_dragon:
            return self.index == 0xdd
        return self.itemtype in [0x94, 0x95]

    @property
    def is_shield(self):
        if self.is_dragon:
            return self.index == 0xee
        return self.itemtype in [0x96]

    @property
    def is_helmet(self):
        if self.is_dragon:
            return self.index == 0xf4
        return self.itemtype in [0x93]

    @property
    def is_fishing(self):
        return self.itemtype in [0xf7]

    @property
    def rank(self):
        if self.index == 0x3e:
            rank = 8000
        elif self.key_item or self.price == 0 or not self.display_name:
            rank = -1
        elif self.equippable and (self.get_bit("cant_be_sold")
                                  or self.price <= 1
                                  or self.index in [0xad]):
            rank = (self.power ** 1.5) * 50
        else:
            rank = self.price
            if self.equippable:
                rank += self.power
        return rank

    @property
    def key_item(self):
        return self.get_bit("cant_be_sold") and not self.equippable

    def get_similar(self, same_kind=False, similar_kind=False):
        if self.key_item or self.rank < 0:
            return self
        candidates = [i for i in ItemObject.ranked if
                      i.rank >= 0 and not i.key_item]
        if same_kind:
            candidates = [i for i in candidates if all([
                getattr(i, "is_%s" % t) == getattr(self, "is_%s" % t)
                for t in ["weapon", "armor", "helmet",
                          "shield", "fishing", "accessory"]])]
        elif similar_kind:
            candidates = [i for i in candidates if all([
                getattr(i, "is_%s" % t) == getattr(self, "is_%s" % t)
                for t in ["equippable", "fishing"]])]
        index = candidates.index(self)
        index = mutate_normal(index, maximum=len(candidates)-1)
        return candidates[index]

    def mutate_price(self):
        if self.price <= 14:
            return
        price = mutate_normal(self.price, maximum=65000)
        rounder = 1 if price < 100 else 2 if price < 1000 else 3
        price = round((price * 2) / (10.0 ** rounder))
        price = int(price * (10 ** rounder) / 2)
        self.price = price

    def mutate_equippable(self):
        if self.index <= 0x3e:
            return

        if not self.equip_dict:
            for sx in self.suffixes:
                self.equip_dict[sx] = []
            for i in ItemObject.every:
                if i.index <= 0x5b or i.is_accessory or not i.display_name:
                    continue
                if i.is_dragon or i.itemtype in self.suffix_dict[i.suffix]:
                    self.equip_dict[i.suffix].append(i.equippable)
                else:
                    suffix = random.choice(self.suffix_dict[i.itemtype])
                    self.equip_dict[suffix].append(i.equippable)

        if self.is_accessory:
            while random.randint(1, 25) == 25:
                if self.equippable == 0xff:
                    self.equippable = 0
                self.equippable |= 1 << random.randint(0, 7)

        for typestr in ["weapon", "shield", "helmet", "armor"]:
            if getattr(self, "is_%s" % typestr) and self.suffix is not None:
                if typestr in ["shield", "helmet"]:
                    itemtypes = (self.itemtypes["shield"] +
                                 self.itemtypes["helmet"])
                else:
                    itemtypes = self.itemtypes[typestr]
                itemtype = random.choice(itemtypes)

                suffixes = self.suffix_dict[itemtype]
                suffixes = [
                    s for s in suffixes
                    if len(s) + len(self.display_name) - len(self.suffix) <= 8]
                suffix = random.choice(suffixes)

                display_name = self.display_name[:-len(self.suffix)] + suffix
                if display_name in self.newnames:
                    if self.display_name not in self.newnames:
                        break
                self.newnames.append(display_name)

                self.itemtype = itemtype
                self.equippable = random.choice(self.equip_dict[suffix])
                self.name = display_name + "".join(
                    [chr(0) for _ in xrange(8-len(display_name))])
                assert len(self.name) == 8


class DropObject(TableObject):
    @property
    def items(self):
        return ItemObject.get(self.common), ItemObject.get(self.rare)

    @property
    def rank(self):
        if any([i.rank < 0 for i in self.items]):
            rank = -1
        else:
            rank = int(round(((ItemObject.get(self.common).rank * 3)
                              + ItemObject.get(self.rare).rank)))
        return rank

    def mutate(self):
        items = [i.get_similar() for i in self.items]
        if self.common == self.rare:
            items = sorted(items, key=lambda i: (i.rank, i.index))
        items = [i.index for i in items]
        self.common, self.rare = tuple(items)


class LevelUp:
    pairs = [("hp", "ap"),
             ("strength", "stamina"),
             ("dummy", "agility"),
             ("wisdom", "luck")]

    def __init__(self, level, block):
        self.level = level
        for pair, value in zip(self.pairs, block):
            value = ord(value)
            a, b = pair
            setattr(self, a, value >> 4)
            setattr(self, b, value & 0xf)

    def __repr__(self):
        s = "%s -" % self.level
        for pair in self.pairs:
            for attr in pair:
                if attr == "dummy":
                    continue
                s += " %s: %s," % (attr, getattr(self, attr))
        return s

    @property
    def max_hp(self):
        return self.hp

    @property
    def max_ap(self):
        return self.ap

    @property
    def block(self):
        block = ""
        for a, b in self.pairs:
            assert getattr(self, a) <= 0xf
            assert getattr(self, b) <= 0xf
            value = (getattr(self, a) << 4) | (getattr(self, b))
            block += chr(value)
        return block


class LevelUpObject(TableObject):
    done_shuffled = False
    maxdict = {"hp": 999, "ap": 511,
               "strength": 255, "agility": 511, "stamina": 255,
               "wisdom": 255, "luck": 255
               }

    def read_data(self, filename=None, pointer=None):
        super(LevelUpObject, self).read_data(filename, pointer=pointer)
        self.levels = {}
        for i in xrange(98):
            level_index = i + 2
            block = self.data[i*4:(i+1)*4]
            assert len(block) == 4
            lv = LevelUp(level_index, block)
            self.levels[level_index] = lv

    def write_data(self, filename=None, pointer=None):
        if self.index >= 8:
            return
        self.data = ""
        for i in xrange(98):
            level_index = i + 2
            self.data += self.levels[level_index].block
        assert len(self.data) == 392
        super(LevelUpObject, self).write_data(filename, pointer=pointer)

    def value_at_level(self, attr, level):
        values = [getattr(self.levels[i], attr) for i in xrange(2, level+1)]
        return sum(values)

    def zero_attr(self, attr):
        for level in self.levels.values():
            setattr(level, attr, 0)

    def mutate(self):
        if not LevelUpObject.done_shuffled:
            LevelUpObject.done_shuffled = True
            levelups = [l for l in LevelUpObject.every if l.index <= 7]
            for attr in sorted(self.maxdict):
                ups = [[getattr(l.levels[i], attr) for i in xrange(2, 100)]
                       for l in levelups]
                random.shuffle(ups)
                for l, us in zip(levelups, ups):
                    for i, u in enumerate(us):
                        setattr(l.levels[i+2], attr, u)

        return
        if self.index >= 8:
            return

        for attr in sorted(self.maxdict):
            value = self.value_at_level(attr, 50)
            maxval = self.maxdict[attr]
            value = mutate_normal(value, minimum=1, maximum=maxval,
                                  smart=False)
            targets = {1: 0, 50: value}
            to_add = [99]
            to_add += [3 + random.randint(15*i, 15*(i+1)) for i in xrange(3)]
            to_add = sorted(set(to_add))
            for target in to_add:
                value = int(round(target * (targets[50] / 50.0)))
                value = mutate_normal(value, minimum=1, maximum=maxval,
                                      smart=False)
                targets[target] = value
            self.zero_attr(attr)
            indices = [1] + sorted(targets)
            for a, b in zip(indices, indices[1:]):
                candidates = [self.levels[i+1] for i in range(a, b)]
                points = targets[b] - targets[a]
                while points > 0:
                    if not candidates:
                        break
                    c = random.choice(candidates)
                    setattr(c, attr, getattr(c, attr) + 1)
                    points -= 1
                    if getattr(c, attr) == 0xf:
                        candidates.remove(c)


class TreasureObject(TableObject):
    @property
    def display_name(self):
        try:
            itemname = ItemObject.get(self.contents)
        except IndexError:
            itemname = "UNKNOWN"
        return itemname

    @property
    def item(self):
        return ItemObject.get(self.contents)

    @property
    def rank(self):
        return int(round(self.item.rank))


class ChestObject(TreasureObject):
    def mutate(self):
        self.contents = self.item.get_similar(similar_kind=True).index


class DresserObject(TreasureObject):
    addrdict = {}

    def __repr__(self):
        contents = self.contents
        try:
            itemname = ItemObject.get(contents)
        except IndexError:
            itemname = "UNKNOWN"
        return "%s %x %x %s" % (self.index, self.pointer, self.address,
                                itemname)

    def mutate(self):
        if self.address in self.addrdict:
            self.contents = self.addrdict[self.address]
            return

        self.contents = self.item.get_similar(similar_kind=True).index
        assert self.contents > 0
        self.addrdict[self.address] = self.contents


class MonsterObject(TableObject):
    minmax_dict = {}
    maxdict = {"hp": 65535, "ap": 65535, "luck": 255,
               "atp": 511, "dfp": 511,
               "agl": 511, "ms": 7, "xp": 65535, "gp": 65535}

    def __repr__(self):
        unknown3 = " ".join(["{0:02x}".format(ord(c)) for c in self.unknown])
        s = "{0:02x} {1} {2}".format(
            self.index, unknown3, self.display_name)
        return s

    @property
    def drops(self):
        return DropObject.get(self.treasure_set)

    @property
    def rank(self):
        if not self.display_name:
            return -1

        attrs = ["hp", "ap", "luck", "atp",
                 "dfp", "agl", "ms"]
        if not self.minmax_dict:
            for attr in attrs:
                values = [getattr(m, attr) for m in MonsterObject.every]
                minval = min([v for v in values if v > 0])
                minval = min([v for v in values if v > minval])
                maxval = max([v for v in values])
                maxval = max([v for v in values if v < maxval])
                self.minmax_dict[attr] = minval, maxval
            return self.rank
        attr_ranks = []
        for attr in attrs:
            value = getattr(self, attr)
            minval, maxval = self.minmax_dict[attr]
            value = min(maxval, max(minval, value))
            attr_rank = float(value - minval) / (maxval - minval)
            attr_ranks.append(attr_rank)
        rank = sum(attr_ranks) / len(attr_ranks)
        rank = int(round(rank * 10000))
        return rank

    def mutate_treasure(self):
        if self.drops.rank < 0:
            return
        self.treasure_set = (DropObject.get(self.treasure_set)
                                       .get_similar().index)
        self.treasure_class = mutate_normal(self.treasure_class, maximum=6)

    def mutate_stats(self):
        ranked = MonsterObject.ranked
        modifactor = (ranked.index(self) / float(len(ranked)-1)) / 2.0
        assert modifactor <= 0.50
        for attr in sorted(self.maxdict):
            maxval = self.maxdict[attr]
            value = getattr(self, attr)
            if modifactor > 0:
                value = int(round(value * (1 + modifactor)))
            value = mutate_normal(value, maximum=maxval)
            if attr == "immunity":
                continue
            setattr(self, attr, value)


class LearnObject(TableObject):
    done_shuffled = False

    def __init__(self, filename, index, pointer, endpointer):
        self.filename = filename
        self.pointer = pointer
        self.index = index
        if filename:
            self.read_data(filename, pointer, endpointer)

    @classproperty
    def every(self):
        return get_learn_spells()

    @classmethod
    def get(self, index):
        return [l for l in get_learn_spells() if l.index == index][0]

    @property
    def spells(self):
        return [SpellObject.get(i) for i in self.spell_indexes]

    @property
    def pairs(self):
        return zip(self.levels, self.spells)

    def read_data(self, filename, pointer, endpointer):
        f = open(filename, 'r+b')
        f.seek(pointer)
        self.levels, self.spell_indexes = [], []
        while pointer < endpointer:
            level, spell = tuple(map(ord, f.read(2)))
            if level == 0:
                break
            self.levels.append(level)
            self.spell_indexes.append(spell)
            pointer += 2
        f.close()

    def write_data(self, filename, pointer):
        f = open(filename, 'r+b')
        for level, spell in self.pairs:
            f.seek(pointer)
            f.write(chr(level) + chr(spell.index))
            pointer += 2
        f.seek(pointer)
        f.write(chr(0))
        f.close()
        pointer += 1
        return pointer

    def mutate(self):
        if not LearnObject.done_shuffled:
            candidates = [l for l in LearnObject.every if l.index != 0]
            candidates = [(l, list(l.spell_indexes), list(l.levels))
                          for l in candidates]
            shuffled = list(candidates)
            random.shuffle(shuffled)
            for a, b in zip(candidates, shuffled):
                l, _, _ = a
                _, spell_indexes, levels = b
                l.spell_indexes = list(spell_indexes)
                l.levels = list(levels)
            LearnObject.done_shuffled = True

        spell_indexes = []
        for s in self.spells:
            if "TimeWarp" in s.name:
                spell_indexes.append(s.index)
                continue
            while True:
                index = s.get_similar().index
                if index not in spell_indexes:
                    spell_indexes.append(index)
                    break
        assert len(spell_indexes) == len(self.spell_indexes)
        assert len(set(spell_indexes)) == len(set(self.spell_indexes))

        first_real_level = min([l for l in self.levels if l > 1])
        levels = [l if l > 1 else
                  random.randint(1, first_real_level) for l in self.levels]
        levels = [mutate_normal(l, minimum=1, maximum=99) for l in levels]
        for (i, l) in enumerate(levels):
            while l > 1 and levels.count(l) > 1:
                l += 1
                levels[i] = l
        real_levels = [l for l in levels if l > 1]
        assert len(real_levels) == len(set(real_levels))
        self.levels, self.spell_indexes = levels, spell_indexes
        self.sort_spells()

    def sort_spells(self):
        self.levels, self.spell_indexes = zip(
            *sorted(zip(self.levels, self.spell_indexes)))


class ShopObject(TableObject):
    def __init__(self, filename, index, pointer):
        self.filename = filename
        self.pointer = pointer
        self.index = index
        if filename:
            self.read_data(filename, pointer)

    @classproperty
    def every(self):
        return get_shops()

    @property
    def items(self):
        return [ItemObject.get(i) for i in self.contents]

    def read_data(self, filename, pointer):
        f = open(filename, 'r+b')
        self.contents = []
        while True:
            f.seek(pointer)
            value = ord(f.read(1))
            if value == 0:
                break
            self.contents.append(value)
            pointer += 1
        f.close()

    def write_data(self):
        f = open(self.filename, 'r+b')
        f.seek(self.pointer)
        f.write("".join([chr(c) for c in self.contents]))
        f.close()

    def mutate(self):
        new_contents = []
        for c in sorted(set(self.contents)):
            while True:
                new_item = ItemObject.get(c).get_similar(same_kind=True)
                if new_item not in new_contents:
                    new_contents.append(new_item)
                    break
        new_contents = [i.index for i in new_contents]
        while len(new_contents) < len(self.contents):
            new_contents.append(random.choice(new_contents))
        assert len(new_contents) == len(self.contents)
        self.contents = new_contents


def get_learn_spells(filename=None):
    global g_learns
    if g_learns is not None:
        return list(g_learns)

    pointer = 0x5aa00
    f = open(filename, 'r+b')
    learns = []
    for i in xrange(9):
        f.seek(pointer + (2*i))
        subpointer = pointer + read_multi(f, 2)
        f.seek(pointer + (2*i) + 2)
        endpointer = pointer + read_multi(f, 2)
        l = LearnObject(filename, i, subpointer, endpointer)
        learns.append(l)
    f.close()
    g_learns = learns
    return get_learn_spells()


def write_learn_spells(filename):
    f = open(filename, 'r+b')
    pointer = 0x5aa00
    subpointer = pointer + len(LearnObject.every)
    for l in LearnObject.every:
        f.seek(pointer + (2*l.index))
        write_multi(f, subpointer-0x5aa00, 2)
        subpointer = l.write_data(filename, subpointer)
    f.close()


def fix_initial_spells():
    spares = [i for i in InitialObject.every if i.spell]
    to_make = []
    for l in LearnObject.every:
        character = CharacterObject.get(l.index)
        for level, spell in l.pairs:
            if level <= character.level:
                to_make.append((character.index, level, spell.index))

    charcounter = {}
    random.shuffle(to_make)
    for (i, spare) in enumerate(spares):
        if to_make:
            c_index, level, s_index = to_make.pop()
            if c_index not in charcounter:
                charcounter[c_index] = 0
            else:
                charcounter[c_index] += 1
        spare.value = s_index
        spare.set_char(c_index)
        spare.set_slot(charcounter[c_index])

    for c_index, level, s_index in to_make:
        learn = LearnObject.get(c_index)
        character = CharacterObject.get(c_index)
        while True:
            level += 1
            if level > character.level and level not in learn.levels:
                break
        for (i, (oldlevel, spell)) in enumerate(learn.pairs):
            if spell.index == s_index:
                learn.levels = list(learn.levels)
                learn.levels[i] = level
                learn.sort_spells()
                break


def get_shops(filename=None):
    global g_shops
    if g_shops is not None:
        return list(g_shops)

    pointer = 0x3fac0
    maxpointer = 0x3fbad
    shops = []
    f = open(filename, 'r+b')
    for i in xrange(1000):
        f.seek(pointer)
        s = ShopObject(filename, i, pointer)
        shops.append(s)
        pointer = s.pointer + len(s.contents) + 1
        if pointer > maxpointer:
            break
    else:
        raise Exception("Too many shops.")
    f.close()

    g_shops = shops
    return get_shops()


if __name__ == "__main__":
    if len(argv) >= 2:
        sourcefile = argv[1]
        if len(argv) >= 3:
            seed = int(argv[2])
        else:
            seed = None
    else:
        sourcefile = raw_input("Filename? ")
        seed = raw_input("Seed? ")

    if seed is None or seed == "":
        seed = int(time())
    seed = seed % (10**10)

    outfile = sourcefile.split(".")
    outfile = outfile[:-1] + [str(seed), outfile[-1]]
    txtfile = ".".join(outfile[:-1] + ["txt"])
    outfile = ".".join(outfile)
    copyfile(sourcefile, outfile)
    set_global_table_filename(outfile)
    get_learn_spells(outfile)
    get_shops(outfile)

    all_objects = [g for g in globals().values()
                   if isinstance(g, type) and issubclass(g, TableObject)
                   and g not in [TableObject, TreasureObject]]
    for ao in all_objects:
        ao.every

    if RANDOMIZE:
        random.seed(seed)
        for d in DropObject.every:
            d.mutate()
        random.seed(seed)
        for c in ChestObject.every:
            c.mutate()
        random.seed(seed)
        for d in DresserObject.every:
            d.mutate()
        random.seed(seed)
        for m in MonsterObject.every:
            m.mutate_stats()
            m.mutate_treasure()
        random.seed(seed)
        for i in ItemObject.every:
            i.mutate_price()
            i.mutate_equippable()
        random.seed(seed)
        for s in ShopObject.every:
            s.mutate()
        random.seed(seed)
        for l in LevelUpObject.every:
            l.mutate()
        random.seed(seed)
        for c in CharacterObject.every:
            c.set_initial_equips()
            c.set_initial_stats()
        random.seed(seed)
        for l in LearnObject.every:
            l.mutate()
        fix_initial_spells()

    # NO RANDOMIZATION PAST THIS LINE

    special_write = [LearnObject]
    for ao in all_objects:
        if ao in special_write:
            continue
        for o in ao.every:
            o.write_data()

    ryu = CharacterObject.get(0)
    ryu.some_index = 9
    ryu.write_data(pointer=ryu.pointer + 0x240)
    bow = CharacterObject.get(1)
    bow.some_index = 0xa
    bow.write_data(pointer=bow.pointer + 0x240)

    write_learn_spells(outfile)

    s = ""
    for ao in sorted(all_objects, key=lambda a: a.__name__):
        s += ao.__name__.upper() + "\n"
        s += ao.catalogue
        s += "\n\n"
    s = s.strip()
    f = open(txtfile, "w+")
    f.write(s + "\n")
    f.close()
