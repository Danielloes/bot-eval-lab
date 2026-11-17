import copy

import pytest

from bot_eval_lab.dataset import load_inputs
from bot_eval_lab.decision import Assistant
from bot_eval_lab.retrieval import LexicalRetriever
from bot_eval_lab.runner import evaluate


@pytest.fixture
def inputs():
    return load_inputs(split="dev")


@pytest.fixture
def policies(inputs):
    return inputs[2]


@pytest.fixture
def assistant(policies):
    return Assistant(LexicalRetriever(policies))


@pytest.fixture(scope="session")
def measured_pair():
    dataset, corpus, policies = load_inputs(split="dev")
    return (evaluate(Assistant(LexicalRetriever(policies)), dataset, corpus),
            evaluate(Assistant(LexicalRetriever(policies, buggy=True)), dataset, corpus))


@pytest.fixture
def runs(measured_pair):
    return copy.deepcopy(measured_pair)
