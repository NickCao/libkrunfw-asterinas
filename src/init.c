/* SPDX-License-Identifier: MIT */
/* Mount the root share and hand PID 1 to libkrun's unmodified guest init. */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <net/if.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

static void fail(const char *operation)
{
    perror(operation);
    for (;;) pause();
}

static void directory(const char *path)
{
    if (mkdir(path, 0755) && errno != EEXIST) fail(path);
}

int main(int argc, char **argv)
{
    (void)argc;
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    directory("/newroot");
    if (mount("/dev/root", "/newroot", "virtiofs", 0, NULL)) fail("mount /dev/root");
    if (chdir("/newroot") || chroot(".") || chdir("/")) fail("chroot");
    directory("/dev");
    if (mount("devtmpfs", "/dev", "devtmpfs", 0, NULL) && errno != EBUSY) fail("mount /dev");
    const char *links[][2] = {
        {"/proc/self/fd", "/dev/fd"}, {"/proc/self/fd/0", "/dev/stdin"},
        {"/proc/self/fd/1", "/dev/stdout"}, {"/proc/self/fd/2", "/dev/stderr"},
    };
    for (size_t i = 0; i < sizeof(links) / sizeof(links[0]); ++i)
        if (symlink(links[i][0], links[i][1]) && errno != EEXIST) fail(links[i][1]);

    /* Asterinas still uses a fixed IPv4 configuration. Avoid upstream init's
     * DHCP client, and let passt learn the guest MAC before inbound traffic. */
    unsetenv("KRUN_DHCP");
    int network = socket(AF_INET, SOCK_DGRAM, 0);
    struct ifreq iface = { .ifr_name = "eth0" };
    if (network >= 0 && !ioctl(network, SIOCGIFADDR, &iface)) {
        struct sockaddr_in gateway = { .sin_family = AF_INET, .sin_port = htons(9) };
        inet_pton(AF_INET, "10.0.2.2", &gateway.sin_addr);
        if (sendto(network, "", 1, 0, (struct sockaddr *)&gateway, sizeof(gateway)) < 0)
            perror("announce guest network");
    }
    if (network >= 0) close(network);
    argv[0] = "/init.krun";
    execv(argv[0], argv);
    fail("exec libkrun guest init");
    return 125;
}
