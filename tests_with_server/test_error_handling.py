from rhizo.main import c


def test_error_handling():
    c.error('this is a test error')
    c.sleep(2)  # sleep a moment for messages to get sent


if __name__ == '__main__':
    test_error_handling()
