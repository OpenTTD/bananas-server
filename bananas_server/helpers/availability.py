from openttd_protocol.protocol.content import Availability


def get_int_value_from_string_name(availability):
    match availability:
        case "savegames-only":
            return Availability.AVAILABILITY_SAVEGAMES_ONLY
        case "new-games":
            return Availability.AVAILABILITY_NEW_GAMES
    return Availability.AVAILABILITY_INVALID
