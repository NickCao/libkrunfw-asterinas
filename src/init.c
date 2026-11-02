/* SPDX-License-Identifier: MIT */
/* Minimal guest bootstrap: mount libkrun's root share and run the OCI command. */
#define _GNU_SOURCE
#include <errno.h>
#include <json-c/json.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static void stop(int status)
{
    fprintf(stderr, "ASTERINAS_POC_EXIT=%d\n", status);
    fflush(NULL);
    sync();
    /* The host PoC launcher observes the status and tears down the VM. */
    for (;;) pause();
}

static void fail(const char *operation)
{
    perror(operation);
    stop(125);
}

static void directory(const char *path)
{
    if (mkdir(path, 0755) && errno != EEXIST) fail(path);
}

static void mount_fs(const char *source, const char *path, const char *type)
{
    directory(path);
    if (mount(source, path, type, 0, NULL) && errno != EBUSY) fail(path);
}

static struct json_object *field(struct json_object *object, const char *name)
{
    struct json_object *value = NULL;
    json_object_object_get_ex(object, name, &value);
    return value;
}

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    puts("Asterinas libkrunfw bootstrap");
    directory("/newroot");
    if (mount("/dev/root", "/newroot", "virtiofs", 0, NULL)) fail("mount /dev/root");
    if (chdir("/newroot") || chroot(".") || chdir("/")) fail("chroot");
    mount_fs("devtmpfs", "/dev", "devtmpfs");
    mount_fs("proc", "/proc", "proc");
    mount_fs("sysfs", "/sys", "sysfs");
    mount_fs("devpts", "/dev/pts", "devpts");
    mount_fs("tmpfs", "/dev/shm", "tmpfs");

    struct json_object *config = json_object_from_file("/.krun_config.json");
    struct json_object *process = config ? field(config, "process") : NULL;
    if (!process) {
        fputs("Missing OCI process configuration\n", stderr);
        stop(125);
    }
    char **command = NULL;
    const char *workdir = "/";
    {
        struct json_object *args = field(process, "args");
        size_t count = args ? json_object_array_length(args) : 0;
        if (!count || count > 4096) {
            fputs("Invalid OCI process.args\n", stderr);
            stop(125);
        }
        command = calloc(count + 1, sizeof(char *));
        if (!command) fail("calloc");
        for (size_t i = 0; i < count; ++i)
            command[i] = (char *)json_object_get_string(json_object_array_get_idx(args, i));
        struct json_object *cwd = field(process, "cwd");
        if (cwd) workdir = json_object_get_string(cwd);
        struct json_object *user = field(process, "user");
        if (user && (json_object_get_int(field(user, "uid")) || json_object_get_int(field(user, "gid")))) {
            fputs("This proof of concept supports guest uid/gid 0 only\n", stderr);
            stop(125);
        }
        struct json_object *env = field(process, "env");
        clearenv();
        for (size_t i = 0; env && i < json_object_array_length(env); ++i) {
            char *item = strdup(json_object_get_string(json_object_array_get_idx(env, i)));
            if (!item || putenv(item)) fail("putenv");
        }
    }
    if (workdir && chdir(workdir)) fail("workdir");
    pid_t child = fork();
    if (child < 0) fail("fork");
    if (!child) {
        execvpe(command[0], command, environ);
        int saved_errno = errno;
        perror(command[0]);
        _exit(saved_errno == ENOENT ? 127 : 126);
    }
    int status;
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) fail("waitpid");
    }
    stop(WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status));
    return 125;
}
