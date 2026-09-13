# Admission writer correction

2026-09-13. Preparation check 36af0d verified the 20 bound text files, then failed before writing the drain admission: Set-Content has no NoClobber parameter. No native observation started and no admission file was created by that call. Retain its exit 1.

Use File.Open with FileMode.CreateNew to write the same reviewed admission JSON without overwriting an existing file. Verify the preparation seal again. The generated drain scope, source hashes and reviewed launcher remain unchanged. Only after that preparation exits 0 may root invoke the native drain observation once. Cancel remains unadmitted.
