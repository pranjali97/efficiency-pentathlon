import json
import sys

import torch
import transformers
from transformers import MBartForConditionalGeneration, MBartTokenizer


# We provide this
def stdio_predictor_wrapper(predictor):
    """
    Wrap a predictor in a loop that reads from stdin and writes to stdout.
    The predictor implements `predict` function that takes a single string and returns the label.

    Assumes each input instance ends with "\n".
    """
    for line in sys.stdin:
        line = line.rstrip()
        inputs = json.loads(line)
        assert isinstance(inputs, list)
        # Participants need to connect their inference code to our wrapper through the following line.
        outputs = predictor.predict(inputs=inputs)
        # Writes are \n deliminated, so adding \n is essential to separate this write from the next loop iteration.
        outputs = [o for o in outputs]
        sys.stdout.write(f"{json.dumps(outputs)}\n")
        # Writes to stdout are buffered. The flush ensures the output is immediately sent through the pipe
        # instead of buffered.
        sys.stdout.flush()


# Submission
class MBART():
    def __init__(self):
        device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
        self.model = MBartForConditionalGeneration.from_pretrained("facebook/mbart-large-en-ro").half().to(device)
        self.tokenizer = MBartTokenizer.from_pretrained("facebook/mbart-large-en-ro", src_lang="en_XX")

        # TODO
        #self._convert_fn = lambda text: text["input"]

    def predict(self, inputs):
        # inputs = [self._convert_fn(i) for i in inputs]
        inputs = self.tokenizer.batch_encode_plus(
            inputs,
            padding=True,
            truncation="only_first",
            return_tensors="pt",
            pad_to_multiple_of=8,
        ).input_ids
        inputs = inputs.to(self.model.device)
        outputs = self.model.generate(inputs, max_length=10)
        outputs = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)
        for output in outputs:
            yield output.strip()


if __name__ == "__main__":
    # We read outputs from stdout, and it is crucial to surpress unnecessary logging to stdout
    transformers.logging.set_verbosity(transformers.logging.CRITICAL)
    transformers.utils.logging.disable_progress_bar()
    classifier = MBART()
    stdio_predictor_wrapper(classifier)