/* Native bundle entry, so codesign can seal the app's main executable. */
#include <mach-o/dyld.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern char **environ;

static int clear_environment(void) {
    /* unsetenv compacts environ: recheck this index after every removal. */
    for (size_t i = 0; environ[i];) {
        if (strncmp(environ[i], "DYLD_", 5) != 0) { ++i; continue; }
        char *end = strchr(environ[i], '=');
        if (!end) return -1;
        char *name = strndup(environ[i], (size_t)(end - environ[i]));
        if (!name) return -1;
        int result = unsetenv(name);
        free(name);
        if (result) return -1;
    }
    const char *names[] = {"PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP",
                           "PYTHONUSERBASE", "PYTHONEXECUTABLE", NULL};
    for (size_t i = 0; names[i]; ++i) {
        if (unsetenv(names[i])) return -1;
    }
    return 0;
}

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
    if (snprintf(python, sizeof(python), "%s/Resources/Python/bin/python3", resolved) >= (int)sizeof(python) ||
        snprintf(script, sizeof(script), "%s/Resources/%s", resolved,
                 (argc == 1 || strcmp(argv[1], "--helper") == 0) ? "uoink_supervisor.py" : "server.py") >= (int)sizeof(script)) return 1;
    if (access(python, X_OK) || access(script, R_OK)) {
        fputs("Uoink installation is incomplete. Reinstall Uoink.app from the DMG.\n", stderr); return 1;
    }
    if (clear_environment()) { perror("Uoink: cannot clear launch environment"); return 1; }
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1); setenv("PYTHONNOUSERSITE", "1", 1);
    char **args = calloc((size_t)argc + 4, sizeof(char *));
    if (!args) return 1;
    args[0] = python; args[1] = "-B"; args[2] = "-s"; args[3] = script;
    /* Login startup requests the helper entry instead of a CLI operation. */
    int first = argc > 1 && strcmp(argv[1], "--helper") == 0 ? 2 : 1;
    for (int i = first; i < argc; ++i) args[i - first + 4] = argv[i];
    execv(python, args);
    perror("Uoink: cannot start bundled Python");
    free(args);
    return 1;
}
