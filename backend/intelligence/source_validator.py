def calculate_source_confidence(
    source_count,
    source_strength=0
):

    if source_count >= 5:
        return 95

    elif source_count == 4:
        return 85

    elif source_count == 3:
        return 75

    elif source_count == 2:
        return 60

    elif source_count == 1:

        if source_strength >= 90:
            return 70

        elif source_strength >= 80:
            return 60

        elif source_strength >= 70:
            return 50

        else:
            return 30

    return 0