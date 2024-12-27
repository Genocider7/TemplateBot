import cv2
import numpy
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Models.ReturnInfo import ReturnInfo

def find_biggest_rectangle(image: numpy.array, bgr_color: list[int], hue_range: int, saturation_range: int, value_range: int) -> ReturnInfo:
    ret = ReturnInfo(returnCode=0, Messages={
        1: 'No color found'
    })
    hsv_color = numpy.array([[bgr_color]], numpy.uint8)
    hsv_color = cv2.cvtColor(hsv_color, cv2.COLOR_BGR2HSV)
    h, s, v = (int(number) for number in hsv_color[0, 0])
    hsv_picture = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lower_bound = numpy.array([max(0, h - hue_range // 2), max(0, s - saturation_range // 2), max(0, v - value_range // 2)], numpy.uint8)
    upper_bound = numpy.array([min(179, h + hue_range // 2), min(255, s + saturation_range // 2), min(255, v + value_range // 2)], numpy.uint8)
    binary_mask = cv2.inRange(hsv_picture, lower_bound, upper_bound)
    contours, hierarchy = cv2.findContours(binary_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if len(contours) == 0 or hierarchy is None:
        ret.returnCode = 1
        return ret
    hierarchy = hierarchy[0]
    biggest_area = 0
    biggest_contour = None
    for i in range(len(contours)):
        if hierarchy[i][3] != -1:
            continue
        area = cv2.contourArea(contours[i])
        next_id = hierarchy[i][2]
        while(next_id != -1):
            area -= cv2.contourArea(contours[next_id])
            next_id = hierarchy[next_id][0]
        if area > biggest_area:
            biggest_area = area
            biggest_contour = contours[i]
    if biggest_contour is None:
        ret.returnCode = 1
        return ret
    rect = cv2.boundingRect(biggest_contour)
    #format it to (top, left, down, right)
    rect = (rect[1], rect[0], rect[1] + rect[3], rect[0] + rect[2])
    ret.returnValue = rect
    return ret

# size_rect is a rectangle containing locations for second image to appear in the first: (Y inital, X initial, Y final, X final)
def insert_image_into_image(Image_background: numpy.array, Image_element: numpy.array, size_rect: tuple[int, int, int, int]) -> ReturnInfo:
    y_initial = size_rect[0]
    x_initial = size_rect[1]
    y_final = size_rect[2]
    x_final = size_rect[3]
    ret = ReturnInfo(returnCode=0, Messages={
        1: 'Incorrect size of the target area',
        2: 'Image array is empty'
    })
    if y_initial < 0 or x_initial < 0:
        ret.returnCode = 1
        return ret
    background_height, background_width, _ = Image_background.shape
    if not all((background_height, background_width)):
        ret.returnCode = 2
        return ret
    if y_final >= background_height or x_final >= background_width:
        ret.returnCode = 1
        return ret
    inserting_image = cv2.resize(Image_element, (x_final - x_initial + 1, y_final - y_initial + 1), interpolation=cv2.INTER_LINEAR)
    returnImage = numpy.copy(Image_background)
    for y in range(y_initial, y_final + 1):
        for x in range(x_initial, x_final + 1):
            returnImage[y][x] = inserting_image[y - y_initial][x - x_initial]
    ret.returnValue = returnImage
    return ret

def wrap_text(text: str, max_width: int, font: int | float, font_scale: int, thickness: int) -> list[str]:
    words = text.split(' ')
    word_lines = []
    current_line = words[0]
    for word in words[1:]:
        (current_width, _), _ = cv2.getTextSize(current_line + ' ' + word, font, font_scale, thickness)
        if current_width <= max_width:
            current_line += ' ' + word
        else:
            word_lines.append(current_line)
            current_line = word
    word_lines.append(current_line)
    return word_lines

def write_on_image(image: numpy.array, text: str, font: int, font_scale: int | float, color: tuple[int, int, int], thickness: int, line_type: int, textarea: tuple[int, int, int, int]) -> ReturnInfo:
    ret = ReturnInfo(returnCode = 0, okCodes = [0, 1], Messages={
        1: 'The bounding box is too small to contain all text. Consider lowering the font scale.',
        2: 'The textarea is not correct',
        3: 'Image array is empty'
    })
    image_height, image_width, _ = image.shape
    if not all((image_height, image_width)):
        ret.returnCode = 3
        return ret
    # Textarea are points (top, left, down, right)
    if any(number < 0 for number in textarea) or textarea[0] >= textarea[2] or textarea[1] >= textarea[3] or textarea[2] > image_height or textarea[3] > image_width:
        ret.returnCode = 2
        return ret
    return_image = numpy.copy(image)
    (_, text_height), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    text_height += baseline
    lines = wrap_text(text, textarea[3] - textarea[1], font, font_scale, thickness)
    current_height = textarea[0] + text_height
    for line in lines:
        cv2.putText(return_image, line, (textarea[1], current_height), font, font_scale, color, thickness, line_type)
        current_height += text_height
    if current_height > textarea[2]:
        ret.returnCode = 1
    ret.returnValue = return_image
    return ret

def show_fields(image: numpy.array, field_coordinates: list[tuple[int, int, int, int]], field_names: list[str], color: tuple[int, int, int] = (255, 0, 0), thickness: int = 1) -> ReturnInfo:
    field_image = numpy.copy(image)
    ret = ReturnInfo(returnCode=0)
    for i in range(len(field_coordinates)):
        pt1 = (field_coordinates[i][1], field_coordinates[i][0])
        pt2 = (field_coordinates[i][3], field_coordinates[i][2])
        cv2.rectangle(field_image, pt1, pt2, color, thickness)
        max_width = pt2[0] - pt1[0]
        estimated_size = max_width/len(field_names[i])/19.1
        result = write_on_image(field_image, field_names[i], cv2.FONT_HERSHEY_SIMPLEX, estimated_size, color, thickness, cv2.LINE_8, field_coordinates[i])
        if not result:
            return result
        field_image = result.returnValue
    ret.returnValue = field_image
    return ret

def hex_to_bgr(hexcode: str) -> ReturnInfo:
    ret = ReturnInfo(returnCode=0, Messages={
        1: '\"{}\" is not a correct hex code'.format(hexcode)
    })
    letters = '0123456789ABCDEF'
    if hexcode.startswith('#'):
        code = hexcode[1:].upper()
    else:
        code = hexcode.upper()
    if len(code) != 6 or not all([letter in letters for letter in code]):
        ret.returnCode = 1
        return ret
    red = 16*letters.find(code[0]) + letters.find(code[1])
    green = 16*letters.find(code[2]) + letters.find(code[3])
    blue = 16*letters.find(code[4]) + letters.find(code[5])
    ret.returnValue = (blue, green, red)
    return ret
    