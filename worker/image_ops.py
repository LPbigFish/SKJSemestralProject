import numpy as np


def invert(img_array: np.ndarray) -> np.ndarray:
    return 255 - img_array


def flip_horizontal(img_array: np.ndarray) -> np.ndarray:
    return img_array[:, ::-1, :]


def crop(img_array: np.ndarray, params: dict) -> np.ndarray:
    top = params.get("top", 0)
    left = params.get("left", 0)
    bottom = params.get("bottom", img_array.shape[0])
    right = params.get("right", img_array.shape[1])

    h, w = img_array.shape[:2]

    if top < 0 or left < 0 or bottom > h or right > w:
        raise ValueError(
            f"Crop bounds ({top},{left})-({bottom},{right}) "
            f"out of image dimensions ({h},{w})"
        )
    if top >= bottom or left >= right:
        raise ValueError(
            f"Invalid crop bounds: top={top} >= bottom={bottom} "
            f"or left={left} >= right={right}"
        )

    return img_array[top:bottom, left:right, :]


def adjust_brightness(img_array: np.ndarray, params: dict) -> np.ndarray:
    value = params.get("value", 0)
    result = img_array.astype(np.int16) + value
    return np.clip(result, 0, 255).astype(np.uint8)


def grayscale(img_array: np.ndarray) -> np.ndarray:
    r = img_array[:, :, 0].astype(np.float64)
    g = img_array[:, :, 1].astype(np.float64)
    b = img_array[:, :, 2].astype(np.float64)
    gray = 0.299 * r + 0.587 * g + 0.114 * b
    gray_uint8 = gray.astype(np.uint8)
    return np.stack([gray_uint8, gray_uint8, gray_uint8], axis=2)


OPERATIONS = {
    "invert": lambda arr, _: invert(arr),
    "flip": lambda arr, _: flip_horizontal(arr),
    "crop": lambda arr, params: crop(arr, params),
    "brightness": lambda arr, params: adjust_brightness(arr, params),
    "grayscale": lambda arr, _: grayscale(arr),
}


def apply_operation(
    img_array: np.ndarray, operation: str, params: dict | None = None
) -> np.ndarray:
    if operation not in OPERATIONS:
        raise ValueError(f"Unknown operation: {operation}")
    return OPERATIONS[operation](img_array, params or {})
