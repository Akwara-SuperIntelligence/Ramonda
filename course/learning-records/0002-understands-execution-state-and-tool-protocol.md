# Understands execution state and the tool-call protocol

After lesson 01, the learner explained, without prompting, why a crash leaves the file on disk but no record in the execution state, and why the agent then does not know the file exists. They also asked — and then correctly restated — that the model predicts the tool name and fills the schema's arguments, while the harness executes and validates. Evidence: their own summary ("the disk and the execution state disagree"), their question sequence about the JSON transport, and their final "it fills in the schema of the one it predicts".

**Implications:** do not re-teach the loop or the request/response protocol. Lesson 02 can go straight to the journal, and the learner is ready for the durable-execution idea. Future lessons can use terms like intent, result, and replay without a definitions detour.
