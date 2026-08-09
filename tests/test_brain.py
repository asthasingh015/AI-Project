def test_brain_modules_exist():
    import brain.persona
    import brain.identity
    import brain.knowledge
    import brain.memory
    import brain.opinion
    import brain.duplicate
    import brain.reflection

    assert brain.persona is not None
    assert brain.identity is not None
    assert brain.knowledge is not None
    assert brain.memory is not None
    assert brain.opinion is not None
    assert brain.duplicate is not None
    assert brain.reflection is not None