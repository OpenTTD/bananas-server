from openttd_protocol.protocol.content import ContentType


content_type_folder_name_mapping = {
    ContentType.CONTENT_TYPE_BASE_GRAPHICS: "base-graphics",
    ContentType.CONTENT_TYPE_NEWGRF: "newgrf",
    ContentType.CONTENT_TYPE_AI: "ai",
    ContentType.CONTENT_TYPE_AI_LIBRARY: "ai-library",
    ContentType.CONTENT_TYPE_SCENARIO: "scenario",
    ContentType.CONTENT_TYPE_HEIGHTMAP: "heightmap",
    ContentType.CONTENT_TYPE_BASE_SOUNDS: "base-sounds",
    ContentType.CONTENT_TYPE_BASE_MUSIC: "base-music",
    ContentType.CONTENT_TYPE_GAME: "game-script",
    ContentType.CONTENT_TYPE_GAME_LIBRARY: "game-script-library",
}


def get_folder_name_from_content_type(content_type):
    return content_type_folder_name_mapping[content_type]


def get_content_type_from_name(content_type_name):
    for content_type, name in content_type_folder_name_mapping.items():
        if name == content_type_name:
            return content_type
    raise Exception("Unknown content_type: ", content_type_name)
