// ATLAS has no release channel yet. Never pull the upstream repository into this build.
namespace Atticus;
static class Updater
{
    public static string Status = "Updates are not available in this development build.";
    public static bool Pending => false;
    public static void Check(Action done) { done(); }
    public static void Schedule() { }
}
