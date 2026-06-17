# Sequence Execution

The {class}`~seercontrol.core.imaging.sequencer.SequencePlan` defines a multi-step
acquisition plan. The {class}`~seercontrol.workers.sequence_worker.SequenceWorker`
executes it on a QThread.

:::{note}
The Graphviz source (`sequence_execution.dot`) for this diagram was lost and needs to be regenerated. The description below covers the execution flow.
:::

## Plan expansion

{func}`~seercontrol.core.imaging.sequencer.expand_plan` converts a `SequencePlan`
(which has steps with `count=` and `start_index=`) into a flat ordered iterator of
{class}`~seercontrol.core.imaging.sequencer.FrameSpec` objects. Each `FrameSpec`
carries everything needed to shoot one frame.

## Per-frame logic

For each `FrameSpec`, the worker:

1. **Filter change** — if the filter name differs from the previous frame, move the
   filter wheel and wait for it to settle.
2. **Autofocus** — if `autofocus_on_filter_change` or `autofocus_every_n` frames have
   elapsed, signal the controller and block until autofocus completes.
3. **Expose** — `start_exposure → poll ImageReady → download`.
4. **QA metrics** — compute HFD, star count, sky ADU, FWHM (best-effort; failure
   doesn't abort).
5. **Write FITS** — Siril-compatible folder structure + full headers.
6. **Emit signals** — `frame_saved(path, record)` for the log, `progress(done, total, eta)`
   for the progress bar.

## Dithering

Dither requests are logged but skipped — the Seestar S30 Pro has no guiding port, so
dithering is a no-op.
