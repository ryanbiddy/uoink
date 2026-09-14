The post-run display command 8fc97d returned exit 1 because its final read used the nonexistent name `child-stdout.log`. The same command's directory listing showed the actual retained receipt is `stdout.json`; earlier reads in that command successfully displayed the checked result and both exits. The conversion itself had already completed as 2827f8/exit 0.

The repair is limited to reading the observed `stdout.json` name. No source, measurement, checkpoint or converted output is rerun or reopened. The failed display remains recorded; the corrected passive display 54e4f4 returned exit 0.
