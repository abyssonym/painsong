from tablereader import TableObject, set_global_table_filename
from utils import read_multi, write_multi, classproperty, mutate_normal, random
from shutil import copyfile
from os import path


try:
    from sys import _MEIPASS
    tblpath = path.join(_MEIPASS, "tables")
except ImportError:
    tblpath = "tables"

spell_level_file = path.join(tblpath, "spell_level_table.txt")

g_learns = None
g_shops = None


class UnknownObject(TableObject):
    pass


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
    def set_initial_equips(self):
        if self.index == 8:
            index = 7 - 4
        else:
            index = 7 - self.index
        mask = 1 << index
        candidates = [i for i in ItemObject.ranked if i.equippable & mask]
        self.weapon = [i for i in candidates if i.is_weapon][:2][-1].index
        self.shield = [i for i in candidates if i.is_shield][:2][-1].index
        self.helmet = [i for i in candidates if i.is_helmet][:2][-1].index
        self.armor = [i for i in candidates if i.is_armor][:2][-1].index


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

    def get_similar(self):
        if self.key_item or self.rank < 0:
            return self
        candidates = [i for i in ItemObject.ranked if
                      i.rank >= 0 and not i.key_item]
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
    def block(self):
        block = ""
        for a, b in self.pairs:
            assert getattr(self, a) <= 0xf
            assert getattr(self, b) <= 0xf
            value = (getattr(self, a) << 4) | (getattr(self, b))
            block += chr(value)
        return block


class LevelUpObject(TableObject):
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
        if self.index == 8:
            print "WARNING! This will overwrite other data!"
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
        maxdict = {"hp": 999, "ap": 511,
                   "strength": 255, "agility": 511, "stamina": 255,
                   "wisdom": 255, "luck": 255
                   }
        for attr in sorted(maxdict):
            value = self.value_at_level(attr, 50)
            maxval = maxdict[attr]
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
        self.contents = self.item.get_similar().index


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

        self.contents = self.item.get_similar().index
        assert self.contents > 0
        self.addrdict[self.address] = self.contents


class MonsterObject(TableObject):
    minmax_dict = {}
    maxdict = {"hp": 65535, "ap": 65535, "luck": 255,
               "atp": 511, "dfp": 511,
               "agl": 511, "ms": 7, "immunity": 255,
               "xp": 65535, "gp": 65535}

    def __repr__(self):
        unknown3 = " ".join(["{0:02x}".format(ord(c)) for c in self.unknown3])
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
                 "dfp", "agl", "ms", "immunity"]
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
        if self.immunity > 0x40:
            modifactor = (ranked.index(self) / float(len(ranked)-1)) / 2.0
            assert modifactor <= 0.50
        else:
            modifactor = 0
        for attr in sorted(self.maxdict):
            maxval = self.maxdict[attr]
            value = getattr(self, attr)
            if modifactor > 0:
                value = int(round(value * (1 + modifactor)))
            value = mutate_normal(value, maximum=maxval)
            setattr(self, attr, value)


class LearnObject(TableObject):
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
    filename = "bof2.smc"
    testfile = "test.smc"
    copyfile(filename, testfile)
    set_global_table_filename(testfile)
    get_learn_spells(testfile)
    get_shops(testfile)

    all_objects = [g for g in globals().values()
                   if isinstance(g, type) and issubclass(g, TableObject)
                   and g not in [TableObject, TreasureObject]]
    for ao in all_objects:
        ao.every

    def hexstring(value):
        if type(value) is str:
            value = "".join(["{0:0>2}".format("%x" % ord(c)) for c in value])
        elif type(value) is int:
            value = "{0:0>2}".format("%x" % value)
        return value

    '''
    #print "FISHCHESTS"
    #for c in ChestObject.every[-8:]:
    #    print c
    #for i, m in enumerate(MonsterObject.every):
    #    print m.display_name, ["%x" % ord(c) for c in m.unknown3]
    #    m.unknown3 = "".join([chr(j) for j in [0x92, 0x4a, 0xfe]])
    #    m.write_data(testfile)

    for ch in CharacterObject.every:
        a = ch.name
        b = hexstring(ch.unknown2)
        c = hexstring(ch.unknown1)
        d = hexstring(ch.unknown3)
        #d = "".join(["{0:0>2}".format("%x" % i) for i in map(ord, ch.unknown4)])
        print "{0:4} {2:2} {1:2} {3:14}".format(a, b, c, d),
        #print "{0:4} {2:18} {3:14}".format(a, None, c, d),
        print "%x %x" % (ch.some_index, ch.pointer)

    for i in ItemObject.every:
        print hexstring(i.index), hexstring(i.itemtype), hexstring(i.unknown), hexstring(i.equippable), i.display_name, i.is_helmet
        #print hexstring(i.index), hexstring(i.equippable), i.display_name

    import string
    for i in ItemObject.every:
        if len(i.display_name) >= 2:
            if i.display_name[-1] in string.uppercase and i.display_name[-2] in string.uppercase:
                #print hexstring(i.itemtype), i.display_name[-2:], i.display_name
                pass
            else:
                print hexstring(i.itemtype), i.display_name[-2:], i.display_name

    for s in SpellObject.every:
        print "%x" % s.index, hexstring(s.unknown1), hexstring(s.unknown2), hexstring(s.element),
        print s.name

    ryu = CharacterObject.get(0)
    for ch in CharacterObject.every:
        #ch.copy_data(ryu)
        ch.some_index = ryu.some_index
        ch.write_data()

    for m in MonsterObject.every:
        print hexstring(m.unknown), m.display_name
    #write_learn_spells(testfile)

    for l in LevelUpObject.every:
        l.mutate()
        l.write_data()

    for c in ChestObject.every:
        c.mutate()
        c.write_data()

    for d in DresserObject.every:
        d.mutate()
        d.write_data()

    for s in ShopObject:
        s.write_data()

    for c in CharacterObject.every[:9]:
        c.set_initial_equips()

    for u in UnknownObject:
        print hexstring(u.index), hexstring(u.index >> 5), hexstring(u.unknown)
    '''
    for i in ItemObject.every:
        print "%x" % i.index, i.display_name, hexstring(i.equippable)
        i.mutate_equippable()
        print "%x" % i.index, i.display_name, hexstring(i.equippable)
