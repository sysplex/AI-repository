"""T09 负向验证临时文件：故意失败的用例。"""


def test_negative_probe() -> None:
    assert 1 + 1 == 3, "intentional failure for T09 negative verification"
