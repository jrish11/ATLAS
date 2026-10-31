// Development-only native dialogs. No WebView event can create these sessions.
using System.Drawing;
using System.Windows.Forms;

namespace Atlas.NativeApprovalDev;

internal static class NativeApprovalDialog
{
    // Native read-only, scrollable full text; the default button is Deny.
    private static bool Show(IWin32Window owner, string title, string content)
    {
        if (owner == null || string.IsNullOrEmpty(content) || content.Length > 15000) return false;
        using var form = new Form { Text = title, Size = new Size(780, 580), StartPosition = FormStartPosition.CenterParent,
                                    MinimizeBox = false, MaximizeBox = false, ShowInTaskbar = false };
        using var detail = new TextBox { Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Both, WordWrap = false,
                                         Dock = DockStyle.Fill, Text = content, AccessibleName = "Complete approval request" };
        using var buttons = new FlowLayoutPanel { Dock = DockStyle.Bottom, Height = 55, FlowDirection = FlowDirection.RightToLeft };
        using var deny = new Button { Text = "Deny", DialogResult = DialogResult.No, AutoSize = true };
        using var allow = new Button { Text = "Allow once", DialogResult = DialogResult.Yes, AutoSize = true };
        buttons.Controls.Add(deny); buttons.Controls.Add(allow); form.Controls.Add(detail); form.Controls.Add(buttons);
        form.CancelButton = deny; form.AcceptButton = deny;
        return form.ShowDialog(owner) == DialogResult.Yes;
    }

    internal static ApprovalSession ConfirmTask(IWin32Window owner, string task, string project)
    {
        if (string.IsNullOrWhiteSpace(task) || task.Length > 2048 || string.IsNullOrWhiteSpace(project) || project.Length > 2048 ||
            !Path.IsPathFullyQualified(project) || !ApprovalSession.DisplaySafe(task) || !ApprovalSession.DisplaySafe(project)) return null;
        var canonical = Path.GetFullPath(project);
        var text = $"Task:\r\n{task}\r\n\r\nProject:\r\n{canonical}\r\n\r\nRequested scope: workspace-write; network-disabled\r\n\r\nContinue only if you intend this exact task and project. Additional actions ask separately.";
        if (!Show(owner, "ATLAS — approve task", text)) return null;
        return new ApprovalSession(task, canonical, "workspace-write; network-disabled", () => DateTimeOffset.UtcNow, TimeSpan.FromMinutes(5));
    }

    internal static bool ConfirmAction(IWin32Window owner, ApprovalRequest request)
    {
        if (request == null || request.Payload.Length > 8192) return false;
        var text = $"Task:\r\n{request.Task}\r\n\r\nProject:\r\n{request.Project}\r\n\r\nScope:\r\n{request.Scope}\r\n\r\nComplete provider request:\r\n{request.Payload}\r\n\r\nAllow this one request?";
        return Show(owner, "ATLAS — approve action", text);
    }
}
