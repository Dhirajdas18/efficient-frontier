import pytest

from ef.cli import main


def test_unknown_topic_exits():
    with pytest.raises(SystemExit):
        main(["report", "nope"])
