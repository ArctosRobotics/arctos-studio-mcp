"""The MCP tool catalog and framing shared by Studio and its stdio adapter."""

import json
import math


MAX_MESSAGE = 4 * 1024 * 1024
NUMBER = {"type": "number"}
INDEX = {"type": "integer", "minimum": 0}
NAME = {"type": "string", "minLength": 1, "maxLength": 160}
PATH = {"type": "string", "minLength": 1, "maxLength": 4096}


def array(items, minimum, maximum):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


def fields(required=(), **properties):
    return {"type": "object", "properties": properties, "required": list(required),
            "additionalProperties": False}


def vector(description, **limits):
    return dict(array({**NUMBER, **limits}, 3, 3), description=description)


def tool(name, description, schema, *, read_only=False, additive=False):
    return {"name": name, "description": description, "inputSchema": schema,
            "annotations": {"readOnlyHint": read_only, "destructiveHint": not (read_only or additive),
                            "openWorldHint": False}}


POSITION = vector("World XYZ in metres, with Z up.", minimum=-10000, maximum=10000)
ANGLE = dict(NUMBER, minimum=-360000, maximum=360000)
ROTATION = vector("Absolute XYZ Euler angles in degrees.", minimum=-360000, maximum=360000)
YAW = dict(ANGLE, description="Base rotation about +Z in degrees.")
SCALE = vector("Absolute scale multipliers along local XYZ.", minimum=0.000001, maximum=1000000)
COLOR = vector("RGB channels between 0 and 1.", minimum=0, maximum=1)
LENGTH = dict(NUMBER, minimum=0.000001, maximum=10000)
SIZE = dict(array(LENGTH, 3, 3), description="Box dimensions along XYZ in metres.")
BOOLEAN = {"type": "boolean"}
JOINTS = {"type": "object", "additionalProperties": dict(NUMBER, minimum=-1e9, maximum=1e9),
          "minProperties": 1, "maxProperties": 64,
          "description": "Joint name to absolute degrees (rotary) or millimetres (linear)."}
DURATION = dict(NUMBER, minimum=.05, maximum=120)
JOINT_WAYPOINTS = array(fields(("joint_positions", "duration_s"), joint_positions=JOINTS, duration_s=DURATION), 1, 100)
INDICES = dict(array(INDEX, 1, 200), uniqueItems=True)
POSE = {"position_m": POSITION, "rotation_deg": ROTATION, "scale": SCALE}
RESULT_POINTER = {"type": "string", "maxLength": 512, "pattern": r"^(?:/(?:[^~/]|~[01])*)*(?![\s\S])",
                  "description": "JSON Pointer into the step result, such as /added/0/index. An empty string refers to the full result."}
WORKFLOW_BINDING = fields(("argument", "step", "pointer"), argument=NAME,
                          step={"type": "integer", "minimum": 1, "maximum": 25}, pointer=RESULT_POINTER)
WORKFLOW_EXPECTATION = fields(("pointer", "equals"), pointer=RESULT_POINTER,
                              equals={"type": ["boolean", "number", "string", "null"]})


def choice(*values):
    return {"type": "string", "enum": list(values)}


def primitive(kind, required, **properties):
    return fields(("kind", "position_m", *required), kind=choice(kind), position_m=POSITION,
                  rotation_deg=ROTATION, name=NAME, color_rgb=COLOR, **properties)


PRIMITIVE = {"type": "object", "oneOf": [
    primitive("box", ("size_m",), size_m=SIZE),
    primitive("cylinder", ("radius_m", "height_m"), radius_m=LENGTH, height_m=LENGTH,
              segments={"type": "integer", "minimum": 3, "maximum": 128}),
    primitive("sphere", ("radius_m",), radius_m=LENGTH),
    primitive("polygon", ("radius_m", "height_m", "sides"), radius_m=LENGTH, height_m=LENGTH,
              sides={"type": "integer", "minimum": 3, "maximum": 128}),
]}

TOOLS = [
    tool("get_scene", "Inspect robots, joint units and limits, and editable mesh models in the active Studio scene. "
         "Model indices can change after removals or undo. Paginate models with model_offset and model_limit.",
         fields(model_offset=INDEX, model_limit={"type": "integer", "minimum": 1, "maximum": 200}), read_only=True),
    tool("list_robot_library", "List built-in robot names accepted by add_robots.", fields(), read_only=True),
    tool("add_robots", "Add up to 20 robots to the live scene at explicit base poses. "
         "Each entry needs either a built-in library name or an absolute path to a local URDF. "
         "The native scene undo stack records the batch as one edit.",
         fields(("robots",), robots=array(dict(
             fields(("position_m",), library=NAME, urdf_path=PATH, position_m=POSITION, yaw_deg=YAW),
             oneOf=[{"required": ["library"]}, {"required": ["urdf_path"]}]), 1, 20)), additive=True),
    tool("create_boxes", "Create a grid of up to 200 editable boxes of the same size, or one box with count=1. "
         "Placement advances along +X first and +Y on each new row. The batch is one undoable edit.",
         fields(("size_m", "origin_m"), size_m=SIZE,
                origin_m=vector("World XYZ centre of the first box in metres.", minimum=-10000, maximum=10000),
                count={"type": "integer", "minimum": 1, "maximum": 200, "default": 1},
                columns={"type": "integer", "minimum": 1, "maximum": 200,
                         "description": "Boxes per row. The default puts the boxes in one row."},
                spacing_m=dict(array(dict(NUMBER, minimum=0, maximum=10000), 2, 2),
                               description="Centre-to-centre X and Y spacing. Defaults to 1.25 times the X and Y dimensions."),
                name_prefix=NAME,
                color_rgb=COLOR), additive=True),
    tool("import_models", "Import up to 20 local STL, OBJ, DAE, GLB or glTF files through Studio's native importer. "
         "A file can create multiple mesh entries. Omit position_m to let Studio ground the model. "
         "STL source units follow Studio's millimetre convention. The batch is one undoable edit.",
         fields(("models",), models=array(fields(("path",), path=PATH, position_m=POSITION, rotation_deg=ROTATION), 1, 20)),
         additive=True),
    tool("transform_model", "Apply an absolute position, rotation or scale to one model from get_scene. "
         "Omitted fields retain their current values. This edit can be undone in Studio.",
         dict(fields(("index",), index=INDEX, position_m=POSITION, rotation_deg=ROTATION, scale=SCALE), minProperties=2)),
    tool("pose_robot", "Set named joints on a simulated robot without sending controller commands. "
         "Use get_scene for joint names and units. This places a pose directly, without trajectory or collision planning.",
         fields(("index", "joint_positions"), index=INDEX,
                joint_positions={"type": "object", "additionalProperties": dict(NUMBER, minimum=-1e9, maximum=1e9),
                                 "minProperties": 1, "maxProperties": 64,
                                 "description": "Joint name to absolute degrees (rotary) or millimetres (linear)."})),
    tool("save_scene", "Save the active scene to a new local .arctos file. The path must be absolute. "
         "Existing files are protected from overwrite.", fields(("path",), path=PATH), additive=True),
    tool("open_scene", "Replace the active scene with a local .arctos file. The replacement creates a Studio undo entry.",
         fields(("path",), path=PATH)),
    tool("create_primitives", "Create up to 200 independently placed boxes, cylinders, spheres or extruded regular polygons. "
         "All dimensions and positions are in metres. Z is up. The position is the centre of each shape.",
         fields(("items",), items=array(PRIMITIVE, 1, 200)), additive=True),
    tool("duplicate_models", "Copy models including their geometry and appearance. Supply optional absolute transforms for the copies.",
         fields(("copies",), copies=array(fields(("index",), index=INDEX, **POSE), 1, 200)), additive=True),
    tool("rename_models", "Rename scene models by index. Studio makes duplicate names unique.",
         fields(("models",), models=array(fields(("index", "name"), index=INDEX, name=NAME), 1, 200))),
    tool("delete_models", "Remove scene model indices in one undoable edit. Later indices can change.",
         fields(("indices",), indices=INDICES)),
    tool("set_model_visibility", "Show or hide individual models in the viewport. Hidden model geometry stays in the scene.",
         fields(("indices", "visible"), indices=INDICES, visible=BOOLEAN)),
    tool("select_model", "Select a mesh model in Studio so its gizmo and tree entry can be inspected.",
         fields(("index",), index=INDEX)),
    tool("list_drawings", "Inspect SVG drawings and their transforms in the current scene.", fields(), read_only=True),
    tool("import_drawings", "Import local SVG files as Studio drawings with optional absolute world position and XYZ rotation.",
         fields(("drawings",), drawings=array(fields(("path",), path=PATH, position_m=POSITION, rotation_deg=ROTATION), 1, 20)),
         additive=True),
    tool("delete_drawings", "Remove SVG drawing indices from the scene. Later drawing indices can change.",
         fields(("indices",), indices=INDICES)),
    tool("move_robot_base", "Set a robot's world base position or yaw in the simulation.",
         dict(fields(("index",), index=INDEX, position_m=POSITION, yaw_deg=YAW), minProperties=2)),
    tool("select_robot", "Select a robot in Studio and update its robot controls and tree selection.",
         fields(("index",), index=INDEX)),
    tool("remove_robots", "Remove added robots, their attached grippers, and their program targets from the scene. "
         "Robot 0 is the main robot; keep it in the scene.", fields(("indices",), indices=dict(array(
             {**INDEX, "minimum": 1}, 1, 20), uniqueItems=True))),
    tool("forward_kinematics", "Calculate the current or proposed end-of-chain pose in world coordinates. "
         "Omitted joints keep their current values.", fields(("index",), index=INDEX, joint_positions=JOINTS), read_only=True),
    tool("solve_inverse_kinematics", "Solve a world-space end-of-chain pose and return named joint positions and residuals. "
         "Omit rotation_deg to solve position only. Use pose_robot, preview_joint_path or add_program_targets to use the result.",
         fields(("index", "position_m"), index=INDEX, position_m=POSITION, rotation_deg=ROTATION,
                seed_joint_positions=JOINTS), read_only=True),
    tool("plan_cartesian_waypoints", "Solve an ordered sequence of end-of-chain poses in a named Studio frame (World by default). "
         "Uses the previous solution to seed each next pose. Returns ready-to-use MoveJ targets and joint preview waypoints "
         "only when all goals are reached. Travel between goals uses joint interpolation. Use check_joint_path to inspect "
         "sampled clearance before previewing.", fields(("index", "waypoints"), index=INDEX, frame=NAME,
                seed_joint_positions=JOINTS, waypoints=array(fields(("position_m", "duration_s"),
                    position_m=vector("XYZ in the chosen frame, in metres.", minimum=-10000, maximum=10000),
                    rotation_deg=ROTATION, duration_s=DURATION, name=NAME), 1, 25)), read_only=True),
    tool("check_joint_path", "Sample a proposed joint preview from the robot's current pose. Reports joint-limit violations, "
         "joint travel, peak joint speeds and clearance from the end-of-chain point to model world bounding boxes. "
         "This sampled check covers the end-of-chain point, with an optional radius. It omits arm, gripper and robot geometry.",
         fields(("index", "waypoints"), index=INDEX, waypoints=JOINT_WAYPOINTS,
                clearance_m=dict(NUMBER, minimum=0, maximum=10, default=0),
                model_indices=INDICES, exclude_model_indices=INDICES,
                max_rotary_step_deg=dict(NUMBER, minimum=.1, maximum=45, default=5),
                max_linear_step_mm=dict(NUMBER, minimum=.1, maximum=100, default=5)), read_only=True),
    tool("list_frames", "List Studio coordinate frames with their world poses and parent frames.", fields(), read_only=True),
    tool("transform_points", "Convert XYZ points in metres between two named Studio frames. Use World for world coordinates.",
         fields(("from_frame", "to_frame", "points_m"), from_frame=NAME, to_frame=NAME, points_m=array(POSITION, 1, 200)),
         read_only=True),
    tool("get_program", "Inspect the native robot program, its per-robot target indices and its conveyor step count. "
         "Pass robot_index to read only one robot's targets.", fields(robot_index=INDEX), read_only=True),
    tool("add_program_targets", "Append native MoveJ targets to a robot's timeline. Omit joint_positions to record the current pose. "
         "Targets with partial joint maps inherit the previous pose from this call. Use the timeline in Studio to review them.",
         fields(("robot_index", "targets"), robot_index=INDEX, targets=array(fields(("name",), name=NAME, joint_positions=JOINTS), 1, 100)),
         additive=True),
    tool("remove_program_targets", "Remove timeline targets for a robot using that robot's target indices from get_program.",
         fields(("robot_index", "indices"), robot_index=INDEX, indices=INDICES)),
    tool("rename_program", "Change the active native program's name.", fields(("name",), name=NAME)),
    tool("preview_joint_path", "Animate a simulated robot through a sequence of named joint waypoints. "
         "Each waypoint's duration is the time to reach that point. Uses joint interpolation, with no collision checks. "
         "Poll get_preview_status and use control_preview to pause, resume or stop.",
         fields(("index", "waypoints"), index=INDEX, waypoints=JOINT_WAYPOINTS)),
    tool("get_preview_status", "Return the state and progress of the current or most recent MCP joint preview.", fields(), read_only=True),
    tool("control_preview", "Pause, resume or stop the MCP joint preview. Stop keeps the current simulated pose.",
         fields(("action",), action=choice("pause", "resume", "stop"))),
    tool("get_view", "Inspect the current Studio viewport camera and visible layers.", fields(), read_only=True),
    tool("capture_viewport", "Return a PNG image from the current simulated Studio viewport. "
         "Use as a standalone call after changing the scene or view.",
         fields(max_dimension_px={"type": "integer", "minimum": 128, "maximum": 768, "default": 640}),
         read_only=True),
    tool("set_view", "Fit the active viewport to the scene or select a standard view.",
         fields(("view",), view=choice("fit", "iso", "front", "back", "left", "right", "top", "bottom"))),
    tool("set_view_layers", "Show or hide meshes, target markers and trajectory lines in the current viewport.",
         dict(fields(models=BOOLEAN, targets=BOOLEAN, trajectories=BOOLEAN), minProperties=1)),
    tool("set_physics", "Enable or pause Studio's PyBullet simulation for the open scene.",
         fields(("enabled",), enabled=BOOLEAN)),
    tool("undo_scene_edit", "Undo the last edit in Studio's scene undo stack, including edits made from the UI.", fields()),
    tool("redo_scene_edit", "Redo the next edit from Studio's scene undo stack.", fields()),
    tool("execute_workflow", "Run up to 25 Studio MCP calls in order using their existing argument schemas. "
         "Steps retain their own undo entries. Bind named arguments to earlier results with bindings and use expect "
         "to stop before the next step if a result value differs from what you require. "
         "Outputs are included in the response only for steps with return_result=true.",
         fields(("steps",), steps=array(fields(("tool",), tool=NAME,
                arguments={"type": "object"}, bindings=array(WORKFLOW_BINDING, 1, 32),
                expect=WORKFLOW_EXPECTATION, return_result=BOOLEAN), 1, 25))),
]
TOOLS_BY_NAME = {entry["name"]: entry for entry in TOOLS}


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON numbers must be finite.")
    return number


def decode(data):
    return json.loads(data, parse_float=_finite_float, parse_constant=_finite_float)


def encode(data):
    return (json.dumps(data, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
