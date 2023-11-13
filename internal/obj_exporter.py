import sys
import tempfile
import copy
import shutil
import bpy
import traceback
import os
from pathlib import Path

from .operator_bases import get_collection_classes
from mathutils import Matrix

from .utility import (
    CDataType, CDataTypes, CStruct, CVal_Literal, CVar,
    LocationVector, N64Rotation, PluginError, ScaleVector, dataTypeEnum, prop_split, to_alnum
)

def get_obj_exporter_context() -> "MiniObjectObjExporterProperty":
    return bpy.context.scene.mini_n64_object_exporter.obj

def export_lines_to_file(lines: list[str], base_path: str, filename: str) -> str:
    exp_path = os.path.join(bpy.path.abspath(base_path), filename)
    
    with open(exp_path, 'w', newline='\n') as fp:
        fp.write('\n'.join(lines + ['']))
    return exp_path

class ExportN64ObjectProperties(bpy.types.Operator):
    # set bl_ properties
    bl_idname = "object.expn64obj"
    bl_description = "Export Object Properties to a directory"
    bl_label = "Export Object Properties"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    # Called on demand (i.e. button press, menu item)
    # Can also be called from operator search menu (Spacebar)
    def execute(self, context):
        try:
            exporter = get_obj_exporter_context()
            if context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
                
            export_objects: list["ExportIndividualObjectProperty"] = exporter.export_objects

            if len(export_objects) == 0:
                raise PluginError("No objects set for export.")
            elif len(exporter.export_path) == 0:
                raise PluginError("Must supply an export path.")

            exportable = [e for e in (exporter.translation, exporter.scale, exporter.rotation,) if e]
            if len(exportable) == 0:
                raise PluginError("Must export one value between translation, scale, and rotation.")

            lines = ['#include "types.h"\n']
            lines_header = ['#pragma once\n']

            for exp_obj in export_objects:
                if exp_obj.obj != None:
                    obj: bpy.types.Object = exp_obj.obj
                    obj_props = []
                    matrix_world: Matrix = obj.matrix_world
                    export_props: ObjectExportProperties = exp_obj.export_props
                    c_data_type: CDataType = CDataTypes[exporter.data_type].value
                    
                    if export_props.translation:
                        base_loc = matrix_world.to_translation()
                        if exp_obj.relative_pos and obj.parent:
                            base_loc = base_loc - obj.parent.matrix_world.to_translation()
                            
                        loc_vec = LocationVector(base_loc)
                        loc_vec.set_data_type(c_data_type)
                        obj_props.append(loc_vec)
                    if export_props.rotation:
                        obj_props.append(N64Rotation(obj.matrix_world.to_quaternion()))
                    if export_props.scale:
                        scale_vec = ScaleVector(matrix_world.to_scale())
                        scale_vec.set_data_type(c_data_type)
                        obj_props.append(scale_vec)

                    if export_props.as_struct:
                        for custom_prop in export_props.custom_props:
                            cvl = CVal_Literal(custom_prop.value)
                            obj_props.append(cvl)

                    if not export_props.as_struct and export_props.rotation and len(obj_props) > 1:
                        raise Exception('Ah shit, you cannot export rotations with other properties as an array. Sorry friend. Enable exporting as a struct to continue')
                    if len(obj_props) == 1 and len(export_props.custom_props) <= 0:
                        obj_props = obj_props[0]
                        if export_props.as_struct:
                            raise Exception('Oops, named vectors have not been implemented.')

                    if export_props.as_struct:
                        obj_props = CStruct(obj_props, c_typedef = export_props.struct_typedef)

                    c_var = CVar(exp_obj.var_name, obj_props, c_data_type.c_typedef, exporter.data_type == CDataTypes.s16.name)
                    lines.append(c_var.to_c())
                    lines_header.append(c_var.to_c_extern());

            exp_path = export_lines_to_file(lines, exporter.export_path, exporter.export_filename)
            exp_path_h = export_lines_to_file(lines_header, exporter.export_path, exporter.export_header)
            
            self.report({"INFO"}, f"Exported to {exp_path} and {exp_path_h}")

        except Exception as exc:
            raise exc

        return {"FINISHED"}  # must return a set

(
    AddMiniExportObject,
    RemoveMiniExportObject,
    MoveMiniExportObject,
    DrawMiniExportObject,
    draw_object_list
) = get_collection_classes(
    'exportobjectproperties',
    ('scene.mini_n64_object_exporter.obj',),
    ('export_objects',),
    ('export_objects_active_index',)
)

(
    AddCustomObjectExportProp,
    RemoveCustomObjectExportProp,
    MoveCustomObjectExportProp,
    DrawCustomObjectExportProp,
    draw_custom_object_prop_list
) = get_collection_classes(
    'customobjectproplist',
    ('scene.mini_n64_object_exporter.obj', 'export_props'),
    ('export_objects', 'custom_props'),
    ('export_objects_active_index', 'custom_props_active_index')
)

class MiniN64ObjectPropertyExporterPanel(bpy.types.Panel):
    bl_idname = "object.expn64objpanel"
    bl_label = "N64 Object Prop Exporter"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Mini N64 Object Property Exporter"

    @classmethod
    def poll(cls, context):
        return True

    # called every frame
    def draw(self, context):
        col = self.layout.box().column()
        try:
            col.scale_y = 1.1  # extra padding
            
            exporter = get_obj_exporter_context()

            export_options = col.column()
            prop_split(export_options, exporter, "export_path", "Directory")
            prop_split(export_options, exporter, "export_filename", "Filename")
            prop_split(export_options, exporter, "export_header", "Header Filename")
            prop_split(export_options, exporter, "data_type", "Data Type")

            col.separator(factor=0.25)

            export_props = col.box().column()
            export_props.label(text="Export props")
            # prop_split(export_props, exporter, "translation", "Translation")
            # prop_split(export_props, exporter, "scale", "Scale")
            export_props.prop(exporter, "translation")
            export_props.prop(exporter, "scale")
            
            col.separator(factor=0.5)
            box = col.box()
            box.label(text="Export objects:")
            draw_object_list(box, context)

            if exporter.export_objects_active_index >= 0 and len(exporter.export_objects):
                item = exporter.export_objects[exporter.export_objects_active_index]
                if item.obj is None:
                    return

                box = box.box()
                box.label(text=f"{item.obj.name} export settings:")
                box = box.column(align=True)
                prop_split(box, item, "var_name", "Variable Name")
                box.separator(factor=1)
                exp_props = box.column(align=True)

                exp_props.prop(item.export_props, 'translation', icon='EMPTY_ARROWS')
                exp_props.prop(item.export_props, 'rotation', icon='CON_ROTLIKE')
                exp_props.prop(item.export_props, 'scale', icon='CON_SIZELIKE')

                if item.export_props.translation:
                    exp_props.prop(item, 'relative_pos')
                exp_props.separator(factor=1)

                struct_col = exp_props.column()
                struct_col.prop(item.export_props, 'as_struct')
                if item.export_props.as_struct:
                    struct_col.prop(item.export_props, 'struct_typedef')
                    box.separator(factor=0.5)
                    box.label(text="Custom props:")
                    draw_custom_object_prop_list(box, context)

            col.operator(ExportN64ObjectProperties.bl_idname)
        except Exception as exc:
            col.label(text="error")
            raise exc

def update_name_from_var_name(self: "ExportIndividualObjectProperty", context: bpy.types.Context):
    if self.obj:
        self.name = " ".join([self.obj.name, f"({self.var_name})"])

def on_update_object(self: "ExportIndividualObjectProperty", context: bpy.types.Context):
    if self.obj:
        self.var_name = to_alnum(self.obj.name)

class CustomObjectExportProp(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")
    value: bpy.props.StringProperty(name="Value")

    def draw(self, layout: bpy.types.UILayout, _data: "ExportIndividualObjectProperty", index: int):
        row = layout.row(align=True).split(factor=0.15)
        row.label(text=f"{index}:")
        row.prop(self, 'value', text="")

class ObjectExportProperties(bpy.types.PropertyGroup):
    as_struct: bpy.props.BoolProperty(name="As Struct (Allows custom props)", default=False)
    separate_values: bpy.props.BoolProperty(
        name="Separately exported variables",
        description="Append pos/rot/scale to variable name and export 3 variables",
        default=False
    )
    struct_typedef: bpy.props.StringProperty(name="Struct Typedef", default="struct MyStruct")
    translation: bpy.props.BoolProperty(name="Export Translation", default=True)
    rotation: bpy.props.BoolProperty(name="Export Rotation", default=False)
    scale: bpy.props.BoolProperty(name="Export Scale", default=False)
    custom_props: bpy.props.CollectionProperty(type=CustomObjectExportProp, name="Custom Properties")
    custom_props_active_index: bpy.props.IntProperty(default=0, name="Custom Props Active Index")

class ExportIndividualObjectProperty(bpy.types.PropertyGroup):
    obj: bpy.props.PointerProperty(type=bpy.types.Object, name="Export object", update=on_update_object)
    name: bpy.props.StringProperty(name="Name")
    var_name: bpy.props.StringProperty(name='Variable Name')
    relative_pos: bpy.props.BoolProperty(name='Relative position from parent', default=True)
    
    export_props: bpy.props.PointerProperty(type=ObjectExportProperties)
    
    # var_name: bpy.props.StringProperty('Variable Name', update=update_name_from_var_name)
    
    def draw(self, layout: bpy.types.UILayout, data: "MiniObjectObjExporterProperty", index: int):
        row = layout.row()
        exp_props = row.row(align=True)
        exp_props.enabled = bool(self.obj)

        exp_props.prop(self.export_props, 'translation', icon='EMPTY_ARROWS', text="")
        exp_props.prop(self.export_props, 'rotation', icon='CON_ROTLIKE', text="")
        exp_props.prop(self.export_props, 'scale', icon='CON_SIZELIKE', text="")
        if self.obj:
            row.prop(self, 'obj', text="", icon="OBJECT_DATAMODE")

            row.separator(factor=0.1)
            row.prop(self, 'var_name', text="Var")
        else:
            prop_split(row.row(), self, "obj", "Select object", icon="OBJECT_DATAMODE")

class MiniObjectObjExporterProperty(bpy.types.PropertyGroup):
    export_objects: bpy.props.CollectionProperty(type=ExportIndividualObjectProperty, name="Export Objects")
    export_objects_active_index: bpy.props.IntProperty(default=0, name="Export Objects Active Index")
    export_path: bpy.props.StringProperty(name="Export Path", subtype="FILE_PATH")
    export_filename: bpy.props.StringProperty(name="Filename", default="frames.c")
    export_header: bpy.props.StringProperty(name="Header Filename", default="frames.h")
    data_type: bpy.props.EnumProperty(items=dataTypeEnum, name="Data Type", default=dataTypeEnum[0][0])

    translation: bpy.props.BoolProperty(name="Export Translation", default=True)
    rotation: bpy.props.BoolProperty(name="Export Rotation", default=False)
    scale: bpy.props.BoolProperty(name="Export Scale", default=False)



classes = (
    CustomObjectExportProp,
    ObjectExportProperties,
    ExportN64ObjectProperties,
    AddCustomObjectExportProp,
    RemoveCustomObjectExportProp,
    MoveCustomObjectExportProp,
    DrawCustomObjectExportProp,
    AddMiniExportObject,
    RemoveMiniExportObject,
    MoveMiniExportObject,
    DrawMiniExportObject,
    MiniN64ObjectPropertyExporterPanel,
    ExportIndividualObjectProperty,
    MiniObjectObjExporterProperty,
)

def obj_register():
    for cls in classes:
        bpy.utils.register_class(cls)

# called on add-on disabling
def obj_unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
