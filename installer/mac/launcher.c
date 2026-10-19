/* Native bundle entry, so codesign can seal the app's main executable. */
#include <mach-o/dyld.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    char path[PATH_MAX], resolved[PATH_MAX], python[PATH_MAX], script[PATH_MAX];
    uint32_t size = sizeof(path);
    if (_NSGetExecutablePath(path, &size) || !realpath(path, resolved)) {
        perror("Uoink: cannot locate app"); return 1;
    }
    char *part = strrchr(resolved, '/');
    if (!part) return 1;
    *part = 0;
    part = strrchr(resolved, '/');
    if (!part) return 1;
    *part = 0; /* Contents */
    if (snprintf(python, sizeof(python), "%s/Frameworks/Python/bin/python3", resolved) >= (int)sizeof(python) ||
        snprintf(script, sizeof(script), "%s/Resources/server.py", resolved) >= (int)sizeof(script)) return 1;
    if (access(python, X_OK) || access(script, R_OK)) {
        fputs("Uoink installation is incomplete. Reinstall Uoink.app from the DMG.\n", stderr); return 1;
    }
    unsetenv("PYTHONHOME"); unsetenv("PYTHONPATH"); unsetenv("PYTHONSTARTUP");
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1); setenv("PYTHONNOUSERSITE", "1", 1);
    char **args = calloc((size_t)argc + 4, sizeof(char *));
    if (!args) return 1;
    args[0] = python; args[1] = "-B"; args[2] = "-s"; args[3] = script;
    for (int i = 1; i < argc; ++i) args[i + 3] = argv[i];
    execv(python, args);
    perror("Uoink: cannot start bundled Python");
    free(args);
    return 1;
}
