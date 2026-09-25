"""Circuit Lab - an MCP bridge that lets an AI design, simulate and animate circuits in Blender."""

bl_info = {
    "name": "Circuit Lab (MCP bridge)",
    "author": "Blender-Circuits contributors",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar > Circuit Lab",
    "description": "Design circuits, simulate them and animate electron flow for teaching videos - driven by an "
                   "AI assistant over MCP",
    "category": "Education",
}

try:
    import bpy
except ImportError:  # imported outside Blender (unit tests of the pure-Python modules)
    bpy = None

if bpy is not None:
    from bpy.props import BoolProperty, IntProperty, StringProperty

    from . import server

    class CIRCUITLAB_AddonPreferences(bpy.types.AddonPreferences):
        bl_idname = __name__

        port: IntProperty(name="Port", default=server.DEFAULT_PORT, min=1024, max=65535)
        host: StringProperty(name="Host", default=server.DEFAULT_HOST)
        auto_start: BoolProperty(name="Start bridge automatically", default=False)

        def draw(self, context):
            col = self.layout.column()
            col.prop(self, "host")
            col.prop(self, "port")
            col.prop(self, "auto_start")

    def _prefs():
        addon = bpy.context.preferences.addons.get(__name__)
        return addon.preferences if addon else None

    class CIRCUITLAB_OT_start(bpy.types.Operator):
        bl_idname = "circuitlab.start_server"
        bl_label = "Start MCP Bridge"
        bl_description = "Listen for commands from the Circuit Lab MCP server"

        def execute(self, context):
            p = _prefs()
            try:
                server.start_server(p.host if p else server.DEFAULT_HOST, p.port if p else server.DEFAULT_PORT)
            except OSError as exc:
                self.report({"ERROR"}, "Could not start bridge: %s" % exc)
                return {"CANCELLED"}
            return {"FINISHED"}

    class CIRCUITLAB_OT_stop(bpy.types.Operator):
        bl_idname = "circuitlab.stop_server"
        bl_label = "Stop MCP Bridge"

        def execute(self, context):
            server.stop_server()
            return {"FINISHED"}

    class CIRCUITLAB_OT_rebuild(bpy.types.Operator):
        bl_idname = "circuitlab.rebuild"
        bl_label = "Rebuild Circuit"
        bl_description = "Recreate all components and wires from the stored circuit model"

        def execute(self, context):
            from . import lab
            lab.rebuild_all()
            return {"FINISHED"}

    class CIRCUITLAB_PT_panel(bpy.types.Panel):
        bl_label = "Circuit Lab"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "Circuit Lab"

        def draw(self, context):
            layout = self.layout
            srv = server.get_server()
            running = srv is not None and srv.running
            p = _prefs()
            box = layout.box()
            box.label(text="MCP bridge: %s" % ("running on port %d" % srv.port if running else "stopped"),
                      icon="LINKED" if running else "UNLINKED")
            if running:
                box.operator("circuitlab.stop_server", icon="PAUSE")
            else:
                box.operator("circuitlab.start_server", icon="PLAY")
            if p:
                box.prop(p, "port")
            layout.operator("circuitlab.rebuild", icon="FILE_REFRESH")
            from . import lab
            try:
                circ = lab.load_circuit()
                layout.label(text="%d components, %d wires" % (len(circ.components), len(circ.wires)))
            except Exception:  # noqa: BLE001 - never break the UI
                pass

    CLASSES = (CIRCUITLAB_AddonPreferences, CIRCUITLAB_OT_start, CIRCUITLAB_OT_stop, CIRCUITLAB_OT_rebuild,
               CIRCUITLAB_PT_panel)

    def _auto_start():
        p = _prefs()
        if p and p.auto_start:
            try:
                server.start_server(p.host, p.port)
            except OSError as exc:
                print("Circuit Lab: could not auto-start bridge:", exc)
        return None

    def register():
        from . import animation
        for cls in CLASSES:
            bpy.utils.register_class(cls)
        for handlers in (bpy.app.handlers.frame_change_pre, bpy.app.handlers.render_pre):
            if animation.update_text_tracks not in handlers:
                handlers.append(animation.update_text_tracks)
        bpy.app.timers.register(_auto_start, first_interval=1.0)

    def unregister():
        from . import animation
        server.stop_server()
        for handlers in (bpy.app.handlers.frame_change_pre, bpy.app.handlers.render_pre):
            while animation.update_text_tracks in handlers:
                handlers.remove(animation.update_text_tracks)
        for cls in reversed(CLASSES):
            bpy.utils.unregister_class(cls)
else:  # pragma: no cover
    def register():
        raise RuntimeError("Circuit Lab must be registered inside Blender")

    def unregister():
        pass
