from tablereader import TableObject, set_global_table_filename
from utils import read_multi, write_multi, classproperty
from shutil import copyfile


g_learns = None


class SpellObject(TableObject):
    pass


class CharacterObject(TableObject):
    pass


class ItemObject(TableObject):
    pass


class DropObject(TableObject):
    @property
    def items(self):
        return ItemObject.get(self.common), ItemObject.get(self.rare)


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

    def mutate(self):
        pass


class TreasureObject(TableObject):
    @property
    def display_name(self):
        try:
            itemname = ItemObject.get(self.contents)
        except IndexError:
            itemname = "UNKNOWN"
        return itemname


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
    def __repr__(self):
        unknown3 = " ".join(["{0:02x}".format(ord(c)) for c in self.unknown3])
        s = "{0:02x} {1} {2}".format(
            self.index, unknown3, self.display_name)
        return s

    @property
    def drops(self):
        return DropObject.get(self.treasure_set).items


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

    #print "FISHCHESTS"
    #for c in ChestObject.every[-8:]:
    #    print c
    #for i, m in enumerate(MonsterObject.every):
    #    print m.display_name, ["%x" % ord(c) for c in m.unknown3]
    #    m.unknown3 = "".join([chr(j) for j in [0x92, 0x4a, 0xfe]])
    #    m.write_data(testfile)

    '''
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
        print hexstring(i.index), hexstring(i.unknown1), hexstring(i.unknown2), hexstring(i.weight), i.name

    for s in SpellObject.every:
        print "%x" % s.index, hexstring(s.unknown1), hexstring(s.unknown2),
        print s.name

    ryu = CharacterObject.get(0)
    for ch in CharacterObject.every:
        #ch.copy_data(ryu)
        ch.some_index = ryu.some_index
        ch.write_data()
    '''
    #write_learn_spells(testfile)

    import pdb; pdb.set_trace()
