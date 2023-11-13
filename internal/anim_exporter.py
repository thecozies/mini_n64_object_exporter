import sys
import tempfile
import copy
import shutil
from typing import Union
import bpy
import traceback
import os
from pathlib import Path
from mathutils import Matrix

from .utility import (
    CDataType, CDataTypes, CValue, CValueList, CVar, CVector, CVectorList,
    LocationVector, MultilayerCVectorList, N64Rotation, ObjectData, ObjectDataGatherer, PluginError, ScaleVector, dataTypeEnum
)

def get_anim_exporter_context() -> "MiniObjectAnimExporterProperty":
    return bpy.context.scene.mini_n64_object_exporter.anim  # type: ignore

def get_cdata_for_frames(
    exporter: "MiniObjectAnimExporterProperty",
    anim_data: MultilayerCVectorList,
    name_ext = ""
):
    if len(anim_data) == 0:
        return None

    c_data_type: CDataType = CDataTypes[exporter.data_type].value
    return CVar(
        exporter.export_variable + name_ext,
        anim_data,
        c_data_type.c_typedef,
        exporter.data_type == CDataTypes.s16.name
    )

class ExportN64ObjectAnimations(bpy.types.Operator):
    # set bl_ properties
    bl_idname = "object.animexpn64obj"
    bl_description = "Export Object Animations to a directory"
    bl_label = "Export Object Animations"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    # Called on demand (i.e. button press, menu item)
    # Can also be called from operator search menu (Spacebar)
    def execute(self, context):
        try:
            exporter = get_anim_exporter_context()
            if context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
                
            export_objects: list["ExportObjectProperty"] = exporter.export_objects

            if len(export_objects) == 0:
                raise PluginError("No objects set for export.")
            elif len(exporter.export_path) == 0:
                raise PluginError("Must supply an export path.")
            elif len(exporter.export_variable) == 0:
                raise PluginError("Must supply a variable name.")
            exportable = [e for e in (exporter.translation, exporter.scale, exporter.rotation,) if e]
            if len(exportable) == 0:
                raise PluginError("Must export one value between translation, scale, and rotation.")
            
            start = bpy.context.scene.frame_start
            end = bpy.context.scene.frame_end

            c_data_type: CDataType = CDataTypes[exporter.data_type].value

            # grab basic data for each object and accumulate it
            all_frames: list[ObjectDataGatherer] = []
            for i in range(start, end + 1):
                bpy.context.scene.frame_set(i)
                frame_data = ObjectDataGatherer()
                for exp_obj in export_objects:
                    if exp_obj.obj != None:
                        obj: bpy.types.Object = exp_obj.obj
                        obj_data = ObjectData(obj, relative=False) # TODO: allow relative exports

                        if exporter.translation:
                            obj_data.add_pos_data(c_data_type)
                        if exporter.rotation:
                            obj_data.add_rot_data()
                        if exporter.scale:
                            obj_data.add_scale_data(c_data_type)
                        frame_data.add(obj_data)
                all_frames.append(frame_data)
                frame_data = None

            anim_data: MultilayerCVectorList = []
            anim_data__pos: MultilayerCVectorList = []
            anim_data__rot: MultilayerCVectorList = []
            anim_data__scale: MultilayerCVectorList = []
            
            separated: bool = exporter.separate_values

            # iterate through all frame data, and group/flatten the value lists
            if separated:
                for frame_data in all_frames:
                    pos, rot, scale = frame_data.unpack()
                    if pos:
                        anim_data__pos.append(pos)
                    if rot:
                        anim_data__rot.append(rot)
                    if scale:
                        anim_data__scale.append(scale)
            else:
                for frame_data in all_frames:
                    anim_data.append(frame_data.flatten())
            
            final = ['#include "types.h"\n\n']
            final_header = ["#pragma once", '#include "types.h"\n\n']
            
            def check_and_add_to_export(a_data: MultilayerCVectorList, name_ext = ""):
                cvar = get_cdata_for_frames(exporter, a_data, name_ext=name_ext)
                if cvar is not None:
                    final.append(cvar.to_c())
                    final_header.append(cvar.to_c_extern())

            if separated:
                if len(anim_data__pos) + len(anim_data__rot) + len(anim_data__scale) == 0:
                    raise PluginError("Oopsie it looks like ya didn't have no data to export lmao")

                check_and_add_to_export(anim_data__pos, name_ext="_pos")
                check_and_add_to_export(anim_data__rot, name_ext="_rot")
                check_and_add_to_export(anim_data__scale, name_ext="_scale")
            else:
                if len(anim_data) == 0:
                    raise PluginError("Oopsie it looks like ya didn't have no data to export lmao")
                # reduce the array
                if len(anim_data) == 1:
                    anim_data = anim_data[0] # type: ignore
                check_and_add_to_export(anim_data)

            exp_path = os.path.join(bpy.path.abspath(exporter.export_path), exporter.export_filename)
            with open(exp_path, 'w', newline='\n') as fp:
                fp.write('\n'.join(final))
            
            exported_places = [exp_path]

            if exporter.export_header:
                exp_header_path = os.path.join(bpy.path.abspath(exporter.export_path), exporter.export_header_filename)
                with open(exp_header_path, 'w', newline='\n') as fp:
                    fp.write('\n'.join(final_header))
                exported_places.append(exp_header_path)

            self.report({"INFO"}, f"Exported to {' and '.join(exported_places)}")

        except Exception as exc:
            raise exc

        return {"FINISHED"}  # must return a set

class AddNewN64AnimExportObject(bpy.types.Operator):
    # set bl_ properties
    bl_description = "Add New Exportable Object"
    bl_idname = "object.animaddexpn64obj"
    bl_label = "Add New Export Object"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    # Called on demand (i.e. button press, menu item)
    # Can also be called from operator search menu (Spacebar)
    def execute(self, context):
        exporter = get_anim_exporter_context()
        exporter.export_objects.add()

        return {"FINISHED"}

class RemoveN64AnimExportObject(bpy.types.Operator):
    # set bl_ properties
    bl_description = "Remove Exportable Object"
    bl_idname = "object.animrmexpn64obj"
    bl_label = "Remove Export Object"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    
    index: bpy.props.IntProperty(name="remove index") # type: ignore

    # Called on demand (i.e. button press, menu item)
    # Can also be called from operator search menu (Spacebar)
    def execute(self, context):
        exporter = get_anim_exporter_context()
        exporter.export_objects.remove(self.index)

        return {"FINISHED"}

class MiniN64ObjectAnimationExporterPanel(bpy.types.Panel):
    bl_idname = "object.animexpn64objpanel"
    bl_label = "Mini N64 Object Animation Exporter"
    bl_space_type = "DOPESHEET_EDITOR"
    bl_region_type = "UI"
    bl_category = "Mini N64 Object Animation Exporter"

    @classmethod
    def poll(cls, context):
        return True

    # called every frame
    def draw(self, context):
        col = self.layout.box().column()
        try:
            col.scale_y = 1.1  # extra padding
            
            exporter = get_anim_exporter_context()

            col.prop(exporter, "export_path")
            col.prop(exporter, "export_filename")
            col.prop(exporter, "export_header")
            if exporter.export_header:
                col.prop(exporter, "export_header_filename")
            col.prop(exporter, "export_variable")
            col.prop(exporter, "data_type")

            col.separator(factor=0.25)

            export_props = col.box().column(align=True, heading="Export props")
            export_props.prop(exporter, "translation")
            export_props.prop(exporter, "rotation")
            export_props.prop(exporter, "scale")

            col.separator(factor=0.25)
            export_props.prop(exporter, "separate_values", text="Separate arrays per prop")
            col.separator(factor=0.5)

            box = col.box()
            box.label(text="Export objects")
            for index, exp_obj in enumerate(exporter.export_objects):
                row = box.row()
                row.prop(exp_obj, 'obj', text="")
                if exp_obj != None:
                    row.operator(RemoveN64AnimExportObject.bl_idname, icon="X", text="").index = index
            box.operator(AddNewN64AnimExportObject.bl_idname, text="Add Object", icon="PLUS")

            col.operator(ExportN64ObjectAnimations.bl_idname)
        except Exception as exc:
            col.label(text="error")
            raise exc

class ExportObjectProperty(bpy.types.PropertyGroup):
    obj: bpy.props.PointerProperty(type=bpy.types.Object, name="Export object") # type: ignore
    name: bpy.props.StringProperty(name="Name") # type: ignore

class MiniObjectAnimExporterProperty(bpy.types.PropertyGroup):
    export_objects: bpy.props.CollectionProperty(type=ExportObjectProperty, name="Export Objects") # type: ignore
    export_path: bpy.props.StringProperty(name="Export Path", subtype="FILE_PATH") # type: ignore
    export_filename: bpy.props.StringProperty(name="Filename", default="frames.c") # type: ignore
    export_header: bpy.props.BoolProperty(name="Export header file", default=True) # type: ignore
    export_header_filename: bpy.props.StringProperty(name="Header Filename", default="frames.h") # type: ignore
    export_variable: bpy.props.StringProperty(name="Variable Name", default="blender_export") # type: ignore
    data_type: bpy.props.EnumProperty(items=dataTypeEnum, name="Data Type", default=dataTypeEnum[0][0]) # type: ignore

    separate_values: bpy.props.BoolProperty(
        name="Separately exported arrays",
        description="Append pos/rot/scale to array variable name and export 3 variables",
        default=True
    ) # type: ignore
    translation: bpy.props.BoolProperty(name="Export Translation", default=True) # type: ignore
    rotation: bpy.props.BoolProperty(name="Export Rotation", default=False) # type: ignore
    scale: bpy.props.BoolProperty(name="Export Scale", default=False) # type: ignore

classes = (
    ExportN64ObjectAnimations,
    AddNewN64AnimExportObject,
    RemoveN64AnimExportObject,
    MiniN64ObjectAnimationExporterPanel,
    ExportObjectProperty,
    MiniObjectAnimExporterProperty,
)

def anim_register():
    for cls in classes:
        bpy.utils.register_class(cls)

# called on add-on disabling
def anim_unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
