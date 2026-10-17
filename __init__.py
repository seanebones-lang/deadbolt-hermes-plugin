"""Hermes public registration surface; no middleware or core overrides."""
from .writer import ArtifactWriter


def register(ctx):
    writer = ArtifactWriter(ctx.get_config)
    for name, description, properties, required, handler in [
        ("deadbolt_prepare_write", "Prepare a private exact-action review request for a NEW text file. This grants no permission and does not create the output file. Stop and ask the operator to review it; never approve it yourself.",
         {"path": {"type": "string", "description": "Relative path inside the configured workspace; parent directories must exist."},
          "content": {"type": "string", "description": "Exact UTF-8 content for operator review."}},
         ["path", "content"], writer.prepare),
        ("deadbolt_commit_write", "Create the previously reviewed new text file only if DeadBolt grants exact admission. A denial creates no output. Never automatically retry an admitted/unknown outcome or grant approval through another tool.",
         {"request_id": {"type": "string", "description": "Request ID returned by deadbolt_prepare_write."}},
         ["request_id"], writer.commit),
    ]:
        ctx.register_tool(name=name, toolset="deadbolt", description=description,
                          schema={"name": name, "description": description,
                                  "parameters": {"type": "object", "properties": properties,
                                                 "required": required, "additionalProperties": False}},
                          handler=handler)
