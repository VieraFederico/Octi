"""Offline checks of the evaluation command's dataset sync (spec 03 VC-305)."""

from types import SimpleNamespace
from uuid import uuid4

from eval.scoring import load_questions
from scripts.run_eval import QUESTIONS_FILE, sync_dataset


class FakeLangSmith:
    """Just the dataset calls `sync_dataset` makes, kept in memory."""

    def __init__(self) -> None:
        self.datasets: dict[str, SimpleNamespace] = {}
        self.examples: list[SimpleNamespace] = []
        self.updates = 0

    def has_dataset(self, *, dataset_name: str) -> bool:
        return dataset_name in self.datasets

    def read_dataset(self, *, dataset_name: str) -> SimpleNamespace:
        return self.datasets[dataset_name]

    def create_dataset(self, dataset_name: str, *, description: str) -> SimpleNamespace:
        self.datasets[dataset_name] = SimpleNamespace(id=uuid4(), name=dataset_name)
        return self.datasets[dataset_name]

    def list_examples(self, *, dataset_id) -> list[SimpleNamespace]:
        return [example for example in self.examples if example.dataset_id == dataset_id]

    def create_example(self, *, inputs, outputs, metadata, dataset_id) -> None:
        self.examples.append(SimpleNamespace(id=uuid4(), inputs=inputs, outputs=outputs, metadata=metadata,
                                             dataset_id=dataset_id))

    def update_example(self, example_id, *, inputs, outputs, metadata) -> None:
        example = next(example for example in self.examples if example.id == example_id)
        example.inputs, example.outputs, example.metadata = inputs, outputs, metadata
        self.updates += 1


def test_two_syncs_keep_one_example_per_question() -> None:
    """Syncing the same questions twice leaves 10 examples, one per id; a changed text updates in place."""
    # Given the versioned questions and an empty LangSmith
    questions = load_questions(QUESTIONS_FILE)
    client = FakeLangSmith()
    # When the dataset is synced twice
    sync_dataset(client, questions)
    sync_dataset(client, questions)
    # Then there are 10 examples, no duplicate id, and nothing was rewritten
    ids = [example.metadata["id"] for example in client.examples]
    assert len(ids) == 10
    assert sorted(ids) == sorted(question.id for question in questions)
    assert client.updates == 0
    # When a question's text changes
    changed = [questions[0].model_copy(update={"question": questions[0].question + " (reworded)"}), *questions[1:]]
    sync_dataset(client, changed)
    # Then the same example is updated
    assert len(client.examples) == 10
    assert client.updates == 1
    assert client.examples[0].inputs["question"].endswith("(reworded)")
