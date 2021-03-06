from randomtools.tablereader import TableObject, set_global_table_filename
from randomtools.utils import (
    read_multi, write_multi, classproperty, mutate_normal,
    hexstring, rewrite_snes_title, rewrite_snes_checksum,
    get_snes_palette_transformer, generate_name,
    utilrandom as random)
from shutil import copyfile
from os import path
from sys import argv
from time import time
from math import log
import string


try:
    from sys import _MEIPASS
    tblpath = path.join(_MEIPASS, "tables")
except ImportError:
    tblpath = "tables"

spell_level_file = path.join(tblpath, "spell_level_table.txt")
name_generator_file = path.join(tblpath, "generator.txt")

g_learns = None
g_shops = None
TEST = False
RANDOMIZE = True
VERSION = 2
ELEMENTS = ["fire", "water", "wind", "earth", "holy", "dark"]
AFFINITIES = ["Off", "Def", "Vig", "Wis", "mAP"]
DONE_AFFINITIES = []
CHAOS_FUSIONS = [0x0, 0x2, 0x4, 0x6, 0x8, 0xa, 0xc, 0xe, 0x10, 0x12]
SUPER_FUSIONS = [0x16, 0x18, 0x1a, 0x1c, 0x1e, 0x20, 0x22, 0x24, 0x26]
difficulty = None


def set_difficulty(value):
    global difficulty
    if not isinstance(value, float) and not isinstance(value, int):
        value = 1.0
    difficulty = value
    return difficulty


class ShamanCompat():
    allshamans = {}

    def __init__(self, element):
        assert element not in self.allshamans
        self.allshamans[element] = self
        self.element = element
        self.compatibility = {}

    @classmethod
    def get(cls, element):
        return cls.allshamans[element]

    @classproperty
    def all_elements(cls):
        return [cls.allshamans[key] for key in ELEMENTS]

    def generate_compatibility(self):
        for element in ELEMENTS:
            if element == self.element:
                self.compatibility[element] = None
                continue
            scp = ShamanCompat.get(element)
            if self.element in scp.compatibility:
                self.compatibility[element] = scp.compatibility[self.element]
            else:
                value = random.randint(0, 100) / 100.0
                self.compatibility[element] = value

        for i in range(0, 8):
            if i in self.compatibility:
                continue
            self.compatibility[i] = random.randint(0, 100) / 100.0

        self.affinities = list(AFFINITIES)
        while True:
            random.shuffle(self.affinities)
            if (len(DONE_AFFINITIES) >= 5
                    or self.affinities[0] not in DONE_AFFINITIES):
                DONE_AFFINITIES.append(self.affinities[0])
                break

    def get_compatibility(self, other):
        if isinstance(other, ShamanCompat):
            other = other.element
        elif isinstance(other, CharacterObject):
            other = other.index
        return self.compatibility[other]

    def __repr__(self):
        s = "%s SHAMAN COMPATIBILITY" % self.element.upper()
        s += "\n" + " ".join(self.affinities)
        for element in ELEMENTS:
            if element in ["fire", "earth"]:
                s = s.strip()
                s += "\n"
            if element == self.element:
                s += "{0:5} N/A      ".format(element)
                continue
            value = int(self.compatibility[element] * 5)
            value = min(value, 4)
            value = '*' + ('*' * value)
            s += "{0:5} {1:-<5}    ".format(element, value)
        for i in range(0, 8):
            name = CharacterObject.get(i).display_name
            if name in ["Ryu", "Nina"]:
                s = s.strip()
                s += "\n"
            value = int(self.compatibility[i] * 5)
            value = min(value, 4)
            value = '*' + ('*' * value)
            s += "{0:4} {1:-<5}    ".format(name, value)
        return s.strip()


for e in ELEMENTS:
    ShamanCompat(e)


class ComboObject(TableObject):
    elements = ELEMENTS
    shamans = list(enumerate(elements))
    shamans = dict(shamans + [(b, a) for (a, b) in shamans])
    combos = [(e, None) for e in elements]
    for i in xrange(5):
        head, tail = elements[i], elements[i+1:]
        for e in tail:
            combos.append((head, e))
    combos = list(enumerate(combos))
    combos = (combos + [((a, b), i) for (i, (a, b)) in combos]
              + [((b, a), i) for (i, (a, b)) in combos])
    combos = dict(combos)

    def nullify(self, i):
        self.nullified.append(i)
        self.fusions[i] = 0

    def get_compatibilities(self, i):
        a, b = self.calculate_shamans(i)
        a = ShamanCompat.get(a)
        c = CharacterObject.get(self.index)
        compatibilities = []
        compatibilities.append(a.get_compatibility(c))
        if b is not None:
            b = ShamanCompat.get(b)
            compatibilities.append(b.get_compatibility(c))
            compatibilities.append(b.get_compatibility(a))
        return compatibilities

    def get_all_boosts(self):
        if not hasattr(self, "nullified"):
            self.nullified = []
        for i, _ in enumerate(self.fusions):
            self.get_boosts(i)
        return sorted(self.boostdict.items())

    def get_boosts(self, i):
        if not hasattr(self, "boostdict"):
            self.boostdict = {}
        if i in self.boostdict:
            return self.boostdict[i]
        a, b = self.calculate_shamans(i)
        a = ShamanCompat.get(a)
        c = CharacterObject.get(self.index)
        a_comp = a.get_compatibility(c)
        values = []
        if b is not None:
            b = ShamanCompat.get(b)
            b_comp = b.get_compatibility(c)
            if b_comp > a_comp:
                a, b = b, a
                a_comp, b_comp = b_comp, a_comp
            ab_comp = a.get_compatibility(b)
            reverse, unstable = False, False
            lower, upper = min(a_comp, b_comp), max(a_comp, b_comp)
            if (lower > 0.5 and ab_comp < 0.5
                    and ab_comp < random.triangular(0, lower)):
                reverse = True
            elif (upper < 0.5 and ab_comp > 0.5
                    and ab_comp > random.triangular(upper, 1)):
                unstable = True
            b_comp = max(b_comp, a_comp * ab_comp)
            for affinity in AFFINITIES:
                if unstable:
                    values.append(random.randint(0, random.randint(50, 100)))
                else:
                    a_index = a.affinities.index(affinity)
                    b_index = b.affinities.index(affinity)
                    if reverse:
                        a_index, b_index = 4-a_index, 4-b_index
                    a_val = (a_comp**2) * (100.0 / (2 ** a_index))
                    b_val = (b_comp**2) * (100.0 / (2 ** b_index))
                    values.append(max(a_val, b_val))
        else:
            for affinity in AFFINITIES:
                a_index = a.affinities.index(affinity)
                a_val = a_comp * (50.0 / (2 ** a_index))
                values.append(a_val)
        values = [mutate_normal(v, maximum=100, return_float=True)
                  for v in values]
        values = tuple([round(v/100.0, 3) for v in values])
        self.boostdict[i] = values
        return values

    def harmony(self, i):
        return max(self.get_compatibilities(i))

    def dischord(self, i):
        return 1 - min(self.get_compatibilities(i))

    def resonance(self, i):
        comps = self.get_compatibilities(i)
        value = reduce(lambda (x, y): x*y, comps, 1)
        value = value ** (1/float(len(comps)))

    @classmethod
    def calculate_index(cls, a, b=None):
        assert a is not None
        if isinstance(a, int):
            a = cls.shamans[a]
        if b is not None:
            if isinstance(b, int):
                b = cls.shamans[b]
            (a, b) = tuple(sorted([a, b], key=lambda c: cls.shamans[c]))
        return cls.combos[a, b]

    @classmethod
    def calculate_shamans(cls, i):
        return cls.combos[i]

    def __repr__(self):
        return self.full_description

    @property
    def full_description(self):
        s = hexstring(self.fusions)
        fs = [f for f in FusionObject if (f.index+1) in self.fusions]
        for f in fs:
            index = self.fusions.index(f.index+1)
            shamans = self.calculate_shamans(index)
            s += "\n%s" % f
            s += " %s" % CharacterObject.get(self.index).display_name
            s += " %s" % shamans[0]
            if None not in shamans:
                s += " %s" % shamans[1]
        return s

    def get_fusion(self, a, b=None):
        if b is not None or not isinstance(a, int):
            index = self.calculate_index(a, b)
        else:
            index = a
        index = self.fusions[index]
        if index == 0:
            return None
        return FusionObject.get(index-1)

    def set_fusion(self, index, fusion):
        assert index not in self.nullified
        fusion.Luk = 0
        self.fusions[index] = fusion.index + 1
        boosts = self.get_boosts(index)
        for affinity, boost in zip(AFFINITIES, boosts):
            getattr(fusion, affinity)
            boost = int(round(boost * 255))
            setattr(fusion, affinity, boost)
        harmony = int(round((self.harmony(index)**4)*50))
        dischord = int(round((self.dischord(index)**4)*25))
        shamans = [s for s in self.calculate_shamans(index) if s is not None]
        if len(shamans) == 1:
            harmony = harmony / 4
            dischord = dischord / 4
        if self.index == 0:
            fusion.character = 0
        elif random.randint(1, 100) <= harmony:
            fusion.character = random.choice(SUPER_FUSIONS)
        elif random.randint(1, 100) <= dischord:
            fusion.character = random.choice(CHAOS_FUSIONS)
        else:
            fusion.character = self.index * 2


class FusionObject(TableObject):
    @property
    def charname(self):
        assert not (self.character % 2)
        index = self.character / 2
        try:
            c = CharacterObject.get(index)
        except KeyError:
            return "%x" % self.character
        return "%x %s" % (self.character, c.display_name)

    def __repr__(self):
        s = []
        for attr in ["Off", "Def", "Vig", "mAP", "Wis"]:
            value = int(round(getattr(self, attr) / 2.55))
            value = "{0:0>2}".format(value)
            s.append("%s %s" % (attr, value))
        s = ", ".join(s)
        s = "%x %s - %x" % (self.index+1, s, self.character)
        return s


class UnknownObject(TableObject):
    @property
    def parent(self):
        cands = [u for u in Unknown2Object.every
                 if u.unk_pointer <= (self.pointer & 0xFFFF)]
        parent = max(cands, key=lambda u: u.unk_pointer)
        assert parent.unk_pointer <= (self.pointer & 0xFFFF)
        return parent

    @property
    def grandparent_index(self):
        return self.parent.groupindex


class Unknown2Object(TableObject):
    pass


class FormDataObject(TableObject):
    '''
    FORMAT:
        Every enemy in the formation is separated by a FF byte.
        Each enemy is 3 bytes,
            1 byte enemy ID
            2 bytes enemy graphic
        The most different enemies in any formation is 3.
    '''

    @property
    def formation(self):
        return FormationObject.get(self.index)


class GraphicsObject(TableObject):
    @property
    def palette(self):
        if self.palette_address == 0:
            return None

        palette = [p for p in PaletteObject
                   if self.palette_address == p.pointer & 0xFFFF]
        if len(palette) != 1:
            return None

        return palette[0]


class PaletteObject(TableObject):
    def mutate(self):
        if hasattr(self, "done") and self.done:
            return
        t = get_snes_palette_transformer()
        self.colors = t(self.colors)
        self.done = True


class RecipeObject(TableObject):
    @property
    def item(self):
        return ItemObject.get(self.index+1)

    @property
    def cookable(self):
        for r in RecipeObject.every[:self.index]:
            if r.score == self.score:
                return False
        return True

    @classmethod
    def shuffle_scores(self):
        rs = [r for r in RecipeObject if r.score > 0]
        scores = [r.score for r in rs]
        assert len(set(scores)) == len(scores)
        random.shuffle(scores)
        for s, r in zip(scores, rs):
            r.score = s


class ZoneObject(TableObject):
    @property
    def formations(self):
        return [FormationObject.get(f) for f in self.formation_indexes]

    def mutate(self):
        indexes = sorted(set(self.formation_indexes))
        new_indexes = list(indexes)
        while len(new_indexes) < 8:
            new_indexes.append(random.choice(indexes))
        random.shuffle(new_indexes)
        self.formation_indexes = new_indexes
        assert len(self.formation_indexes) == 8

    def __repr__(self):
        s = "\n".join([str(f) for f in self.formations])
        s = "%x\n%s" % (self.index, s)
        return s


class FormationObject(TableObject):
    original_enemies = {}
    mould_candidates = {}
    moulds = []

    def __repr__(self):
        s = "%x %s: " % (self.index, hexstring(self.mould))
        s += ", ".join(["%x %s" % (e.index, e.display_name)
                        for e in self.enemies])
        return s

    @property
    def formdata(self):
        return FormDataObject.get(self.index)

    @property
    def enemies(self):
        enemies = []
        for eid in self.enemy_ids:
            if eid == 0xFF:
                continue
            m = MonsterObject.get(eid)
            enemies.append(m)
        return enemies

    @property
    def rank(self):
        eranks = [e.rank for e in self.enemies]
        ranks = [sum(eranks) / len(eranks), max(eranks),
                 sum(eranks) / (log(len(eranks))+1)]
        rank = sum(ranks) / len(ranks)
        return rank

    def mutate(self):
        num_different = len(set(self.enemies))
        similars = [f for f in FormationObject if f.mould == self.mould
                    and len(f.enemies) >= num_different]
        chosen = random.choice(similars)
        ids = [e for e in self.enemy_ids if e != 0xFF]
        random.shuffle(ids)
        ordering = range(5)
        random.shuffle(ordering)
        for index in ordering:
            e = chosen.enemy_ids[index]
            if e == 0xFF:
                self.enemy_ids[index] = 0xff
                continue
            for i in ids:
                if i not in self.enemy_ids:
                    self.enemy_ids[index] = i
                    break
            else:
                self.enemy_ids[index] = random.choice(ids)
        return


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
        inits = [i for i in InitialObject.every
                 if i.char == self and i.is_learned_spell]
        inits = sorted(set([i.spell.display_name for i in inits]))
        if inits:
            s += "Starts with %s\n" % ", ".join(inits)
        spellup = LearnObject.get(self.index)
        for level, spell in spellup.pairs:
            if level == 1 and spell.index == 9:
                continue
            s += "lv{0:2} {1}\n".format(level, spell.display_name)
        return s.strip()

    def set_initial_equips(self):
        if self.index == 0:
            return
        if self.index > 8:
            return
        elif self.index == 8:
            index = 7 - 4
        else:
            index = 7 - self.index
        mask = 1 << index
        candidates = [i for i in ItemObject.ranked if i.equippable & mask
                      and i.equippable != 0xFF and i.rank > 0]
        for itemtype in ["weapon", "shield", "helmet", "armor"]:
            typecands = [i for i in candidates
                         if getattr(i, "is_%s" % itemtype)]
            if typecands:
                setattr(self, itemtype, typecands[0].index)
            else:
                setattr(self, itemtype, 0)

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

    def __repr__(self):
        s = "%x %s (%s)" % (self.index, self.display_name, self.price)
        if self.is_equippable:
            s += ": "
            for i in xrange(8):
                if self.equippable & (1 << (7-i)):
                    s += " %s" % CharacterObject.get(i).display_name
        return s

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
    def is_booster(self):
        return self.index in range(0xd, 0x13)

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
        key_item_ids = [0x57]
        if self.index in key_item_ids:
            return True
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
                for t in ["equippable", "fishing", "accessory"]])]
        index = candidates.index(self)
        index = mutate_normal(index, maximum=len(candidates)-1)
        return candidates[index]

    def mutate_price(self):
        if self.is_booster:
            self.price = 4000
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
                    if i.equippable != 0xFF:
                        self.equip_dict[suffix].append(i.equippable)

        if self.is_accessory:
            while random.randint(1, 25) == 25:
                if self.equippable == 0xff:
                    self.equippable = 0
                self.equippable |= 1 << random.randint(0, 7)

        for typestr in ["weapon", "shield", "helmet", "armor"]:
            if getattr(self, "is_%s" % typestr) and self.suffix is not None:
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
    def __repr__(self):
        s = "%x " % self.index
        return s + ", ".join([i.display_name for i in self.items])

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
            itemname = ItemObject.get(self.contents).display_name
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
            itemname = ItemObject.get(contents).display_name
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
        s = "{0:02x} {1}".format(
            self.index, self.display_name)
        return s

    @property
    def graphics(self):
        return GraphicsObject.get(self.index)

    @property
    def palette(self):
        return self.graphics.palette

    def mutate_palette(self):
        if self.is_boss:
            return
        if self.palette is not None:
            self.palette.mutate()

    @property
    def is_boss(self):
        for f in FormationObject:
            if self in f.enemies:
                return False
        return True

    @property
    def is_overworld(self):
        for z in ZoneObject:
            for f in z.formations:
                if self in f.enemies:
                    return True
        return False

    @property
    def drops(self):
        return DropObject.get(self.treasure_set)

    @property
    def rank(self):
        if not self.display_name:
            return -1

        attrs = ["hp", "luck", "atp", "dfp"]
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
        self.xp *= (4.0 / (2**difficulty))
        self.gp *= (4.0 / (2**difficulty))
        ranked = MonsterObject.ranked
        modifactor = (ranked.index(self) / float(len(ranked)-1))
        modifactor = (modifactor ** 2) / 2.0
        modifactor = modifactor * (difficulty**0.5)
        for attr in sorted(self.maxdict):
            maxval = self.maxdict[attr]
            value = getattr(self, attr)
            minimum = min(1, value)
            if modifactor > 0:
                value = int(round(value * (1 + modifactor)))
            value = mutate_normal(value, minimum=minimum, maximum=maxval)
            if attr == "immunity":
                continue
            setattr(self, attr, value)

    @classmethod
    def shuffle_ai(cls):
        monsters = [m for m in MonsterObject.ranked if not m.is_boss]
        for (a, b) in zip(monsters, monsters[1:]):
            if random.choice([True, False]):
                a.ai, b.ai = b.ai, a.ai
                a.ap, b.ap = b.ap, a.ap

    @classmethod
    def shuffle_stats(cls):
        paired = {"dfp": ["hp"],
                  "treasure_set": ["treasure_class"]}
        monsters = [m for m in MonsterObject.ranked if not m.is_boss]
        for (a, b) in zip(monsters, monsters[1:]):
            for attr in ["atp", "dfp", "agl", "ms", "luck", "treasure_set"]:
                if random.choice([True, False]):
                    if attr in paired:
                        to_switch = paired[attr] + [attr]
                    else:
                        to_switch = [attr]
                    for att in to_switch:
                        aa, bb = getattr(a, att), getattr(b, att)
                        setattr(a, att, bb)
                        setattr(b, att, aa)

    @classmethod
    def randomize_names(cls):
        done_names = []
        monsters = [m for m in MonsterObject.ranked if not m.is_boss]
        generate_name(namegen_table=name_generator_file)
        for m in monsters:
            while True:
                name = generate_name(maxsize=8)
                for done_name in done_names:
                    if name in done_name or done_name in name:
                        break
                else:
                    done_names.append(name)
                    while len(name) < 8:
                        name += " "
                    assert len(name) == 8
                    name = name.replace(" ", chr(0))
                    m.name = name
                    break


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

    def add_pair(self, pair):
        level, s_index = pair
        self.levels = tuple(list(self.levels) + [level])
        self.spell_indexes = tuple(list(self.spell_indexes) + [s_index])
        self.sort_spells()

    def set_pairs(self, pairs):
        if not pairs:
            self.levels = []
            self.spell_indexes = []
            return
        self.levels, self.spell_indexes = zip(*pairs)
        if self.spell_indexes and not isinstance(self.spell_indexes[0], int):
            self.spell_indexes = [s.index for s in self.spell_indexes]

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
            if f.tell() >= 0x5aaf8:
                print "Notice: Spell overflow. Planned spells were cut."
                break
            f.seek(pointer)
            f.write(chr(level) + chr(spell.index))
            pointer += 2
        f.seek(pointer)
        assert f.tell() < 0x5ab00
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
            while True:
                BANNED_INDEXES = [0x1e, 0x1f, 0x20]
                index = s.get_similar().index
                if index in BANNED_INDEXES:
                    continue
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
                new_item = ItemObject.get(c).get_similar(similar_kind=True)
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
    subpointer = pointer + (len(LearnObject.every)*2)
    for l in LearnObject.every:
        f.seek(pointer + (2*l.index))
        write_multi(f, subpointer-0x5aa00, 2)
        subpointer = l.write_data(filename, subpointer)
    f.close()


def fix_initial_spells():
    fixed = [(0, 0, 0x20),
             (0, 0, 0x1f),
             (0, 0, 0x1e),
             ]
    spares = [i for i in InitialObject.every if i.spell]
    spares = sorted(spares, key=lambda i: i.addr)
    to_make = []
    for l in LearnObject.every:
        character = CharacterObject.get(l.index)
        for level, spell in l.pairs:
            if level <= character.level:
                to_make.append((character.index, level, spell.index))

    charcounter = {}
    random.shuffle(to_make)
    to_make.extend(reversed(fixed))
    for (i, spare) in enumerate(spares):
        if to_make:
            c_index, level, s_index = to_make.pop()
            if (c_index, level, s_index) not in fixed:
                assert not fixed
            else:
                fixed.remove((c_index, level, s_index))
            if c_index not in charcounter:
                charcounter[c_index] = 0
            else:
                charcounter[c_index] += 1
        spare.value = s_index
        spare.set_char(c_index)
        spare.set_slot(charcounter[c_index])

    for c_index in range(9):
        learn = LearnObject.get(c_index)
        character = CharacterObject.get(c_index)
        learn.set_pairs([(l, s) for (l, s) in learn.pairs
                         if l > character.level])

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

    # the game is weird and skips the first X spells for some reason
    spellskips = {2: 2, 4: 4, 5: 1, 6: 1, 7: 7, 8: 15}
    for key, value in spellskips.items():
        learn = LearnObject.get(key)
        for i in xrange(value):
            learn.add_pair((0x01, 0x09))


def set_warps_free():
    for index in [0x1e, 0x1f, 0x20]:
        SpellObject.get(index).cost = 0


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


def randomize_fusions():
    scomps = ShamanCompat.all_elements
    random.shuffle(scomps)
    for s in scomps:
        s.generate_compatibility()

    all_all_boosts = []
    for c in ComboObject:
        all_boosts = c.get_all_boosts()
        for index, boosts in all_boosts:
            all_all_boosts.append((c.index, index, sum(boosts)))

    all_all_boosts = sorted(all_all_boosts, key=lambda (a, b, c): c)
    for c_index, index, _ in all_all_boosts[:-len(FusionObject.every)]:
        c = ComboObject.get(c_index)
        c.nullify(index)
        all_all_boosts.remove((c_index, index, _))

    all_all_boosts = sorted(all_all_boosts)
    assert len(all_all_boosts) == len(FusionObject.every)
    for i, (c_index, index, _) in enumerate(all_all_boosts):
        c = ComboObject.get(c_index)
        f = FusionObject.get(i)
        c.set_fusion(index, f)


def randomize_othello(filename):
    prizes = [(0x9220, ['SD', 'RP']),
              (0x9255, 'WP'),
              (0x9278, 'BW'),
              (0x929b, 'HT'),
              (0x95e1, 'DR'),
              (0x9616, 'ST'),
              (0x9639, ['AR', 'ML']),
              (0x965C, 'SH')]
    f = open(filename, "r+b")
    for address, types in prizes:
        if not isinstance(types, list):
            types = [types]
        f.seek(address)
        old = ItemObject.get(ord(f.read(1)))
        candidates = [i for i in ItemObject.ranked if i is old
                      or i.display_name[-2:] in types]
        index = candidates.index(old)
        if len(candidates) == 1:
            chosen = old
        else:
            candidates.remove(old)
            if index >= len(candidates):
                chosen = candidates[-1]
            else:
                chosen = random.choice(candidates[index:])
        f.seek(address)
        f.write(chr(chosen.index))
    f.close()


def lower_encounter_rate(filename):
    f = open(filename, 'r+b')
    f.seek(0x32750)
    f.write("".join(map(chr, [0x22, 0x00, 0x49, 0xc5])))
    f.seek(0x54900)
    reduction = [0x4a] * 3
    f.write("".join(map(chr, [0x85, 0x1c] + reduction + [0x6b])))
    f.close()


def randomize():
    def display_flag_options():
        print
        print "\n".join([
            "Choose which things to randomize (blank for all).",
            "f  fusions",
            "t  treasure",
            "m  monsters",
            "n  monster names and palettes",
            "p  shops",
            "q  item equippability",
            "c  character stats",
            "s  character spells",
            "w  cooking and othello",
            ])
        print

    print 'You are using "Breath of Fire II: Painsong" version %s.' % VERSION
    if len(argv) >= 2:
        sourcefile = argv[1]
        if len(argv) >= 3:
            flags = argv[2]
            if not set(flags) & set(string.letters):
                flags = ""
            if len(argv) >= 4:
                seed = int(argv[3])
                if len(argv) >= 5:
                    set_difficulty(float(argv[4]))
                else:
                    set_difficulty(1.0)
            else:
                seed = None
                set_difficulty(1.0)
        else:
            flags = ""
            seed = None
            set_difficulty(1.0)
    else:
        sourcefile = raw_input("Filename? ")
        display_flag_options()
        flags = raw_input("Flags? ")
        seed = raw_input("Seed? ")
        d = raw_input("Difficulty? (default: 1.0) ")
        print
        try:
            d = float(d)
        except ValueError:
            d = 1.0
        set_difficulty(d)

    if not flags.strip():
        flags = string.lowercase

    if seed is None or seed == "":
        seed = int(time())
    else:
        seed = int(seed)
    seed = seed % (10**10)
    print "Using seed: %s" % seed

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
        if 'f' in flags:
            print "Randomizing fusions."
            random.seed(seed)
            randomize_fusions()
        if 't' in flags:
            print "Randomizing treasure."
            random.seed(seed)
            for d in DropObject.every:
                d.mutate()
            for c in ChestObject.every:
                c.mutate()
            for d in DresserObject.every:
                d.mutate()
            for m in MonsterObject.every:
                m.mutate_treasure()
        if 'm' in flags:
            print "Randomizing monsters."
            random.seed(seed)
            for m in MonsterObject.every:
                m.mutate_stats()
            MonsterObject.shuffle_ai()
            MonsterObject.shuffle_stats()
            MonsterObject.get(0x80).atp = 400
            for z in ZoneObject.every:
                z.mutate()
        if 'n' in flags:
            print "Randomizing monster palettes and names."
            random.seed(seed)
            for m in MonsterObject.every:
                m.mutate_palette()
            MonsterObject.randomize_names()
        if 'p' in flags:
            print "Randomizing shops."
            random.seed(seed)
            for i in ItemObject.every:
                i.mutate_price()
            for s in ShopObject.every:
                s.mutate()
        if 'q' in flags:
            print "Randomizing item equippability."
            random.seed(seed)
            for i in ItemObject.every:
                i.mutate_equippable()
            for c in CharacterObject.every:
                c.set_initial_equips()
        if 'c' in flags:
            print "Randomizing character stats."
            random.seed(seed)
            for l in LevelUpObject.every:
                l.mutate()
            for c in CharacterObject.every:
                c.set_initial_stats()
        if 's' in flags:
            print "Randomizing character spells."
            random.seed(seed)
            for l in LearnObject.every:
                l.mutate()
            fix_initial_spells()
            set_warps_free()
        if 'w' in flags:
            print "Randomizing cooking and othello."
            random.seed(seed)
            randomize_othello(outfile)
            RecipeObject.shuffle_scores()

    # NO RANDOMIZATION PAST THIS LINE

    lower_encounter_rate(outfile)

    special_write = [LearnObject]
    for ao in all_objects:
        if ao in special_write:
            continue
        for o in ao.every:
            try:
                o.write_data()
            except NotImplementedError:
                break

    ryu = CharacterObject.get(0)
    ryu.some_index = 9
    ryu.write_data(pointer=ryu.pointer + 0x240)
    bow = CharacterObject.get(1)
    bow.some_index = 0xa
    bow.write_data(pointer=bow.pointer + 0x240)

    write_learn_spells(outfile)

    rewrite_snes_title("BOF2-PS %s" % seed, outfile, VERSION)
    rewrite_snes_checksum(outfile)

    if TEST:
        catobjects = sorted(all_objects, key=lambda a: a.__name__)
    else:
        catobjects = [CharacterObject]

    s = ""
    for ao in catobjects:
        s += ao.__name__.upper() + "\n"
        s += ao.catalogue
        s += "\n\n"

    for scp in ShamanCompat.all_elements:
        s += str(scp) + "\n\n"

    s = s.strip()
    f = open(txtfile, "w+")
    f.write(s + "\n")
    f.close()

    if len(argv) < 2:
        print
        raw_input("Randomization completed successfully. "
                  "Press Enter to close this program.")

if __name__ == "__main__":
    if "test" in argv:
        randomize()
    else:
        try:
            randomize()
        except Exception, e:
            print "ERROR: %s" % e
            raw_input("Press Enter to close this program.")
