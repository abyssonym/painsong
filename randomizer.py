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
            rank = level + (0.001 * index)
            so = SpellObject.get(index)
            self.rankings[so] = rank
        f.close()
        for so in SpellObject.every:
            print so
            assert so in self.rankings
        return self.rank


class CharacterObject(TableObject):
    pass


class ItemObject(TableObject):
    @property
    def rank(self):
        if self.index == 0x3e:
            rank = 8000
        elif self.key_item or not self.display_name:
            return -1
        elif self.equippable and (self.get_bit("cant_be_sold")
                                  or self.price <= 1):
            rank = (self.power ** 1.5) * 50
        else:
            rank = self.price
            if self.equippable:
                rank += self.power
        return rank + (0.001 * self.index)

    @property
    def key_item(self):
        return self.get_bit("cant_be_sold") and not self.equippable


class DropObject(TableObject):
    @property
    def items(self):
        return ItemObject.get(self.common), ItemObject.get(self.rare)

    @property
    def rank(self):
        rank = int(round(((ItemObject.get(self.common).rank * 3)
                          + ItemObject.get(self.rare).rank)))
        return rank + (0.01 * self.index)


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
        return int(round(self.item.rank)) + (0.001 * self.index)


class ChestObject(TreasureObject):
    pass


class DresserObject(TreasureObject):
    def __repr__(self):
        contents = self.contents - 1
        try:
            itemname = ItemObject.get(contents)
        except IndexError:
            itemname = "UNKNOWN"
        return "%s %x %x %s" % (self.index, self.pointer, self.address, itemname)


class MonsterObject(TableObject):
    minmax_dict = {}

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
        return rank + (0.001 * self.index)


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


if __name__ == "__main__":
    filename = "bof2.smc"
    testfile = "test.smc"
    copyfile(filename, testfile)
    set_global_table_filename(testfile)
    get_learn_spells(testfile)

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
        print hexstring(i.index), hexstring(i.equippable), hexstring(i.power), hexstring(i.weight), i.name

    for s in SpellObject.every:
        print "%x" % s.index, hexstring(s.unknown1), hexstring(s.unknown2), hexstring(s.element),
        print s.name

    ryu = CharacterObject.get(0)
    for ch in CharacterObject.every:
        #ch.copy_data(ryu)
        ch.some_index = ryu.some_index
        ch.write_data()
    '''
    for m in MonsterObject.every:
        print hexstring(m.graphics), hexstring(m.unknown3), m.display_name
    #write_learn_spells(testfile)

    for l in LevelUpObject.every:
        l.mutate()

    import pdb; pdb.set_trace()
