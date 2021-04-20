from rhizo.controller import Controller


def test_create_sequence():
    max_history = 1234
    c = Controller()
    base_path = c.path_on_server()

    # create folders
    if not c.files.exists(base_path + '/folder'):
        c.files.create_folder(base_path + '/folder')

    # delete old sequences
    def delete_if_exists(rel_path):
        if c.files.exists(base_path + '/' + rel_path):
            c.files.delete(base_path + '/' + rel_path)
    delete_if_exists('test')
    delete_if_exists('testIntSeq')
    delete_if_exists('testFloatSeq')
    delete_if_exists('folder/testSub')

    # create sequences
    c.sequences.create('test', 'text', min_storage_interval=0)
    c.sequences.create('testIntSeq', 'numeric', decimal_places=0, max_history=max_history, min_storage_interval=0)
    c.sequences.create(base_path + '/testFloatSeq', 'numeric', decimal_places=2, units='degrees_C', min_storage_interval=0)
    c.sequences.create(base_path + '/folder/testSub', 'text', min_storage_interval=0)

    # check sequences
    attrib = c.files.info(base_path + '/test')['system_attributes']
    assert attrib['data_type'] == 2
    assert attrib['min_storage_interval'] == 0
    attrib = c.files.info(base_path + '/testIntSeq')['system_attributes']
    assert attrib['data_type'] == 1
    assert attrib['decimal_places'] == 0
    assert attrib['max_history'] == max_history
    assert attrib['min_storage_interval'] == 0
    attrib = c.files.info(base_path + '/testFloatSeq')['system_attributes']
    assert attrib['data_type'] == 1
    assert attrib['decimal_places'] == 2
    assert attrib['min_storage_interval'] == 0
    assert attrib['units'] == 'degrees_C'
    attrib = c.files.info(base_path + '/folder/testSub')['system_attributes']
    assert attrib['data_type'] == 2
    assert attrib['min_storage_interval'] == 0


if __name__ == '__main__':
    test_create_sequence()
