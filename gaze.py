"""Screen-coordinate gaze selection, adapted from a reviewed DeepSeek candidate."""
import math


def gaze_sector(cursor_x, cursor_y, center_x, center_y, previous=None,
                deadzone=24.0, hysteresis=4.0):
    dx, dy = cursor_x-center_x, cursor_y-center_y
    if dx*dx+dy*dy <= deadzone*deadzone:
        return None
    angle = math.degrees(math.atan2(dx, -dy)) % 360.0
    if previous is not None:
        delta = (angle-previous*22.5+180.0) % 360.0-180.0
        if abs(delta) <= 11.25+hysteresis:
            return previous
    return int(angle/22.5+0.5) % 16
