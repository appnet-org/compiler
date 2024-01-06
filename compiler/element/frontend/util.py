def find_type_index(list, target_type):
    """
    Finds the index of the first occurrence of a specified type in a list.

    Parameters:
    list : list
        The list to search through.
    target_type : type
        The type to find in the list.

    Returns:
    int
        The index of the first occurrence of the specified type in the list.
        Returns -1 if the type is not found in the list.
    """
    for i, item in enumerate(list):
        # Check if the current item is an instance of the target_type
        if isinstance(item, target_type):
            return i  # Return the index of the first occurrence
    return -1  # Return -1 if the type is not found
