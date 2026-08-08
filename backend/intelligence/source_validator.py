def calculate_source_confidence(source_count):

    if source_count >= 5:
        return 95

    elif source_count == 4:
        return 85

    elif source_count == 3:
        return 70

    elif source_count == 2:
        return 50

    elif source_count == 1:
        return 30

    else:
        return 0