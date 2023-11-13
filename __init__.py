import sys
import tempfile
import copy
import shutil
import bpy
import traceback
import os
from pathlib import Path

from .internal.obj_exporter import MiniObjectObjExporterProperty, obj_register, obj_unregister
from .internal.anim_exporter import MiniObjectAnimExporterProperty, anim_register, anim_unregister

# info about add on
bl_info = {
    "name": "Mini N64 Object Data Exporter",
    "version": (0, 0, 1),
    "author": "thecozies",
    "location": "3DView",
    "description": "Plugin for exporting object and animation data as a C array",
    "category": "Import-Export",
    "blender": (3, 0, 0),
}

class MiniObjectExporterProperty(bpy.types.PropertyGroup):
    anim: bpy.props.PointerProperty(type=MiniObjectAnimExporterProperty)
    obj: bpy.props.PointerProperty(type=MiniObjectObjExporterProperty)

classes = (
    MiniObjectExporterProperty,
)

def register():
    obj_register()
    anim_register()
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.mini_n64_object_exporter = bpy.props.PointerProperty(type=MiniObjectExporterProperty)

# called on add-on disabling
def unregister():
    obj_register()
    anim_unregister()
    del bpy.types.Scene.mini_n64_object_exporter

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
