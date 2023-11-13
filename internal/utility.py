import functools
import bpy
from mathutils import Matrix, Vector, Quaternion, Euler
from typing import Any, Iterable, Literal, Optional, Tuple, Union
from enum import Enum
from typing import NewType
from collections.abc import Callable, Iterable
from math import degrees

class PluginError(Exception):
    pass

def to_alnum(name):
    if name is None or name == "":
        return None
    for i in range(len(name)):
        if not name[i].isalnum():
            name = name[:i] + "_" + name[i + 1 :]
    if name[0].isdigit():
        name = "_" + name
    return name

def prop_split(layout: bpy.types.UILayout, data: Any, field: str, name: str, factor=0.5, **prop_kwargs):
    split = layout.split(factor=factor)
    split.label(text=name)
    split.prop(data, field, text="", **prop_kwargs)

def get_blender_to_game_scale(context: bpy.types.Context) -> int:
    match context.scene.gameEditorMode:
        case "SM64":
            return context.scene.blenderToSM64Scale
        case "OOT":
            return context.scene.ootBlenderScale
        case "F3D":
            pass
        case _:
            pass
    return context.scene.blenderF3DScale

transform_mtx_blender_to_n64 = lambda: Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))

tabs = lambda n: n * '    '

# Arg 1 - Number to format
# Arg 2 - Scale (used for going from Blender scale to N64)
# Arg 3 - Format as hexadecimal
CValFormatter = Callable[[Union[float, int, str], float, bool], str]


def format_f32(val: float, scale: float, fmt_hex=False) -> str:
    """Round to 9 to prevent `e` str representation"""
    if fmt_hex:
        raise ValueError(f"value: {val} is a float and cannot be formatted to hexadecimal") 
    return f'{(val * scale):16.10f}f'

def format_integer(val: int, scale: float, fmt_hex=False) -> str:
    if fmt_hex:
        padding = 6
        if abs(val) > 0x8000:
            padding += 4
        return f'{round(val * scale):#0{padding}x}' 
    return f'{round(val * scale):8}'

def format_s32(val: int, scale: float, fmt_hex=False) -> str:
    return format_integer(val, scale, fmt_hex=fmt_hex)

S16_MIN = -32768
S16_MAX = 32767
def format_s16(val: int, scale: float, fmt_hex=False) -> str:
    if val < S16_MIN:
        raise ValueError(f"value: {val} is less than the s16 minimum")
    if val > S16_MAX:
        raise ValueError(f"value: {val} is greater than the s16 maximum")
    return format_integer(val, scale, fmt_hex=fmt_hex)

def format_literal(val: str, _scale: float, fmt_hex=False) -> str:
    return val

def rad_to_s16(x: float):
    return degrees(x) * 0x2000 / 45

def format_s16_rot(val: float, _scale: Any, fmt_hex=True) -> str:
    if val < S16_MIN:
        raise ValueError(f"value: {val} is less than the s16 minimum")
    if val > S16_MAX:
        raise ValueError(f"value: {val} is greater than the s16 maximum")
    n_val = int(round(rad_to_s16(val)))
    return format_integer(n_val, 1, fmt_hex=True)

class CDataType():
    c_typedef: str = ''
    formatter: CValFormatter = None # must be initialized on init

    def __init__(self, c_typedef: str, formatter: CValFormatter):
        self.c_typedef = c_typedef
        self.formatter = formatter
        
    @property
    def enum(self) -> tuple[str, str, str]:
        return (self.c_typedef, self.c_typedef, self.c_typedef,)
    


class CDataTypes(Enum):
    f32 = CDataType('f32', format_f32)
    s32 = CDataType('s32', format_s32)
    s16 = CDataType('s16', format_s16)
    s16_rot = CDataType('s16', format_s16_rot)

c_literal = CDataType('literal', format_literal)


class CType():
    c_data_type: CDataType

    def set_data_type(self, c_data_type: CDataType):
        self.c_data_type = c_data_type

class N64Vec(CType, Vector):
    @classmethod
    def with_ctype(cls, args: Vector, c_data_type: CDataType):
        new_instance = cls(args)
        new_instance.set_data_type(c_data_type)
        return new_instance

    def to_n64(self) -> Vector:
        return transform_mtx_blender_to_n64() @ self

class LocationVector(N64Vec):
    pass

class ScaleVector(N64Vec):
    def to_n64(self) -> Vector:
        n64_vec: Vector = transform_mtx_blender_to_n64() @ self
        n64_vec.z *= -1
        return n64_vec


class N64Rotation(CType, Quaternion):
    c_data_type = CDataTypes.s16_rot.value

    def to_n64(self) -> Vector:
        new_rot: Quaternion = transform_mtx_blender_to_n64() @ self.to_matrix().to_4x4() @ transform_mtx_blender_to_n64().inverted()
        # vector helps with conversion shenanigans just trust me lol
        return Vector(new_rot.to_euler('ZXY'))

class CVal_F(CType, float):
    pass

class CVal_I(CType, int):
    pass

class CVal_Literal(CType, str):
    c_data_type = c_literal
    pass

CVector = LocationVector | ScaleVector | N64Rotation
def set_cvector_type(vec: CVector, c_data_type: CDataType):
    vec.set_data_type(c_data_type)
    return vec

CValue = N64Rotation | N64Vec | CVector | CVal_F | CVal_I | CVal_Literal
CTypeDef = str | Literal["f32"] | Literal["s32"] | Literal["s16"]

# could be a loc/rot/scale list, could be multiple objects singular props, or more
CVectorList = list[CVector]
MultilayerCVectorList = list[CVector | CVectorList | list[CVectorList]]

# same as CVectorList with more flexibility
CValueList = list[CValue]
MultilayerCValueList = list[CValue | CValueList | list[CValueList]] | MultilayerCVectorList

class CStruct(CValueList):
    c_typedef: CTypeDef

    def __init__(self, vals: CValueList, c_typedef: CTypeDef = None):
        super(CStruct, self).__init__(vals)
        self.c_typedef = c_typedef

def join_on_one_line(items: list[str], prefix):
    return prefix + " ".join(["{", ", ".join(items), "}"])

def join_on_new_lines(items: list[str], prefix):
    return f"\n{prefix}".join([
        "{",
        *[f"{tabs(1)}{i}," for i in items],
        "}"
    ])

class CVar():
    var_name: str
    value: CValue | MultilayerCValueList
    array_depth: int = 0
    array_lengths: list[int] = []
    fmt_hex: bool = False
    scale: int = 0 # assigned when formatting
    max_line_size: int = 120
    c_typedef: CTypeDef = 'unknown'
    struct_start: int = -1 # depth where struct starts

    def __init__(
        self,
        var_name: str,
        value: CValue | MultilayerCValueList,
        c_typedef: CTypeDef,
        fmt_hex=False
    ):
        self.var_name = var_name
        self.value = value
        self.fmt_hex = fmt_hex
        self.c_typedef = c_typedef

        # reset other params
        self.array_depth = 0
        self.array_lengths = []
        self.scale = 0 # assigned when formatting
        self.max_line_size = 80
        
    def new_array_depth(self, depth: int, array_len: int):
        if depth > self.array_depth:
            self.array_depth = depth
            self.array_lengths.append(array_len)
        else:
            self.array_lengths[depth - 1] = array_len

    def fmt_vec(self, vec: CVector):
        n64_vec: Vector = vec.to_n64()
        scale = self.scale if type(vec) is LocationVector else 1
        items_str = ', '.join([
            vec.c_data_type.formatter(val, scale, self.fmt_hex)
            for val in n64_vec.xyz
        ])
        return " ".join(["{", items_str, "}"])

    def format_nested(self, value: CValue | list[CValue], depth = 0):
        """Recursively travels through the value to format it's entries"""
        if isinstance(value, N64Vec) or isinstance(value, N64Rotation):
            VEC_LENGTH = 3 # all vectors currently export as "3"
            self.new_array_depth(depth + 1, VEC_LENGTH)
            return self.fmt_vec(value)

        if isinstance(value, Iterable) and type(value) is not CVal_Literal:
            new_depth = depth + 1
            values: list[str] = [] # `Any` b/c potentially recursive
            if type(value) == CStruct:
                self.struct_start = depth
                self.c_typedef = value.c_typedef

            self.new_array_depth(new_depth, len(value)) # set initial len
            for item in value:
                formatted = self.format_nested(item, new_depth)
                values.append(formatted)

            a_len = len(values)
            self.new_array_depth(new_depth, a_len) # ensure len is correct
            
            prefix = tabs(new_depth - 2)
            output = join_on_one_line(values, prefix)
            if len(output) > self.max_line_size:
                prefix = tabs(new_depth - 1)
                output = join_on_new_lines(values, prefix)

            return output
        
        return value.c_data_type.formatter(value, 1, self.fmt_hex)

    def dec_c_var(self) -> str:
        """
            Returns `<ctype> <variable><array_dec> = `\n
            e.g. `f32 my_array[12] = `
        """
        array_dec = ''
        if self.struct_start >= 0:
            self.array_lengths = self.array_lengths[0:self.struct_start]
            self.array_depth = self.struct_start
        if self.array_depth > 0:
            array_dec = ''.join([
                f"[{l}]" for l in self.array_lengths
            ])

        var_dec = self.var_name + array_dec
        decs = [self.c_typedef, var_dec]
        return ' '.join(decs)
    
    def to_c(self):
        self.scale = get_blender_to_game_scale(bpy.context)
        c_array = self.format_nested(self.value)
        dec_vals = ' '.join([self.dec_c_var(), '=', c_array])
        return f"{dec_vals};\n"

    def to_c_extern(self):
        return ' '.join(['extern', self.dec_c_var()]) + ';'


dataTypeEnum = (
    CDataTypes.f32.value.enum,
    CDataTypes.s32.value.enum,
    CDataTypes.s16.value.enum,
)


def reduce_list(l: list):
    if len(l) == 1:
        return l[0]
    return l

class ObjectData:
    position_data: Optional[LocationVector] = None
    scale_data: Optional[ScaleVector] = None
    rotation_data: Optional[N64Rotation] = None
    
    # must be initialized on init
    matrix: Matrix = None # type: ignore
    
    def __init__(self, obj: bpy.types.Object, relative = False):
        self.matrix: Matrix = obj.matrix_world
        if relative and obj.parent:
            p_mat: Matrix = obj.parent.matrix_world
            self.matrix = p_mat.inverted() @ self.matrix
    
    def add_pos_data(self, c_data_type: CDataType):
        self.position_data = LocationVector.with_ctype(self.matrix.to_translation(), c_data_type)

    def add_scale_data(self, c_data_type: CDataType):
        self.scale_data = ScaleVector.with_ctype(self.matrix.to_scale(), c_data_type)

    def add_rot_data(self):
        self.rotation_data = N64Rotation(self.matrix.to_quaternion())
    
    def should_separate_data(self):
        return self.rotation_data and (self.position_data or self.scale_data)

    def get_valid_data(self):
        return [p for p in (self.position_data, self.rotation_data, self.scale_data) if p is not None]

    def get_num_exports(self):
        return sum(1 for _ in self.get_valid_data())
    
    def get_reduced_exports(self) -> CValueList | CValue:
        return reduce_list(self.get_valid_data())


class ObjectDataGatherer:
    """Represents multiple objects in a single frame or export"""
    object_data: list[ObjectData] = []
    
    def __init__(self) -> None:
        self.object_data = []
    
    def add(self, obj_data: ObjectData):
        self.object_data.append(obj_data)

    def flatten(self) -> list[CVectorList] | CVectorList:
        data = [od.get_reduced_exports() for od in self.object_data]
        return reduce_list(data)
    
    def unpack(self) -> Tuple[Optional[CVectorList | CVector], Optional[CVectorList | CVector], Optional[CVectorList | CVector]]:
        pos: Optional[CVectorList] = None
        rot: Optional[CVectorList] = None
        scale: Optional[CVectorList] = None

        for od in self.object_data:
            if od.position_data:
                if pos is None:
                    pos = []
                pos.append(od.position_data)
            if od.rotation_data:
                if rot is None:
                    rot = []
                rot.append(od.rotation_data)
            if od.scale_data:
                if scale is None:
                    scale = []
                scale.append(od.scale_data)
        unpacked = []
        for n in [pos, rot, scale]:
            if n and len(n):
                unpacked.append(reduce_list(n))
            else:
                unpacked.append(None)
        return tuple(unpacked)
