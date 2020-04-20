import enum


# Copy from OpenTTD/src/network/core/tcp_content.h
class PacketTCPContentType(enum.IntEnum):
    PACKET_CONTENT_CLIENT_INFO_LIST = 0  # Queries the content server for a list of info of a given content type
    PACKET_CONTENT_CLIENT_INFO_ID = 1  # Queries the content server for information about a list of internal IDs
    PACKET_CONTENT_CLIENT_INFO_EXTID = 2  # Queries the content server for information about a list of external IDs
    PACKET_CONTENT_CLIENT_INFO_EXTID_MD5 = (
        3  # Queries the content server for information about a list of external IDs and MD5
    )
    PACKET_CONTENT_SERVER_INFO = 4  # Reply of content server with information about content
    PACKET_CONTENT_CLIENT_CONTENT = 5  # Request a content file given an internal ID
    PACKET_CONTENT_SERVER_CONTENT = 6  # Reply with the content of the given ID
    PACKET_CONTENT_END = 7  # Must ALWAYS be on the end of this list!! (period)


class ContentType(enum.IntEnum):
    CONTENT_TYPE_BASE_GRAPHICS = 1  # The content consists of base graphics
    CONTENT_TYPE_NEWGRF = 2  # The content consists of a NewGRF
    CONTENT_TYPE_AI = 3  # The content consists of an AI
    CONTENT_TYPE_AI_LIBRARY = 4  # The content consists of an AI library
    CONTENT_TYPE_SCENARIO = 5  # The content consists of a scenario
    CONTENT_TYPE_HEIGHTMAP = 6  # The content consists of a heightmap
    CONTENT_TYPE_BASE_SOUNDS = 7  # The content consists of base sounds
    CONTENT_TYPE_BASE_MUSIC = 8  # The content consists of base music
    CONTENT_TYPE_GAME = 9  # The content consists of a game script
    CONTENT_TYPE_GAME_LIBRARY = 10  # The content consists of a GS library
    CONTENT_TYPE_END = 11  # Helper to mark the end of the types
