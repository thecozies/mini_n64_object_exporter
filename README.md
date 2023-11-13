# mini n64 object exporter (blender addon)

## overview

this lets you export C values/arrays/structs based on various object properties, like translation, scale, and rotation. it can also export keyframes as an array. rotation is always exported as if it was S16, using `ZXY` rotation order (same as SM64 objects - yaw/pitch/roll). if you don't know, rotation order doesn't mean which variable is x or y or z, it is the order in which rotation should be performed mathematically. the exported rotation array will be x,y,z still (pitch/yaw/roll in sm64)

one day this readme may have more info, but for now i'll be brief.

## use-case examples

- use the object property exporter with scale/translation to export AABBs (axis aligned bounding boxes). in game, check if a position is within these bounds for triggering something
- cutscenes. force a camera in blender to always point at another object, and use the animation export to export positions of both objects. set your camera's position in game to `your_array[cutscene_frame][index of camera positions]` and camera focus to `your_array[cutscene_frame][index of other object's positions]`. you can then animate your camera fully in blender and know almost exactly how it will look shot for shot.

## panels

### animations

- open the menu on the right side of a Timeline panel. it will be titled with the name "Mini N64 Object Animation Exporter"
- choose paths, variable names, etc
- choose what data type or types you want to export the array with. as of the time of writing, only f32 works with scale
- add objects that you want to export to the list
- if you check `Separate arrays per prop`, then rotation/translation/scale arrays will be separated vs one single list with all three embedded - appended with the transform type on each variable
- from Start to End, each keyframe will be exported. the range is inclusive, if Start is 0 and End is 50, you'll export frames 0...50, resulting in 51 frames total
- even if you select a data type that isnt s16, rotation will still be a s16 angle format

### variables

- in the 3D viewport's side panel you'll see Mini N64 Object Property Exporter
- like animations you can supply a path and data types
- hit the plus button to add a new object or variable to export
- you can choose whether or not it exports as a struct, which will allow you to add custom props to the export data
- the order of transform properties in the struct will be translation, rotation, then scale. you could create a struct with that order
- if you want it to export relative to its parent there is an option for that as well.
- you cannot export rotation with other transforms if it is NOT a struct

## future plans

nothing at the moment. if you have a request i will consider it, but otherwise any updates will just be made as i require them. if you want a new version, pay attention to your version number in `__init__.py` - if the released version is a major version bump from where you are, then it will have broken compatibility with what you have already done in some way.

## can i copy this?

sure. this can be a useful base for you to create custom exporters for your particular project. you could add a color field to objects, export your variables into a pointer array, export lights as directions, etc. its designed to let you just group some data up and change it to C and i can't possibly cover every use-case for myself for the future, and likely not for you.
