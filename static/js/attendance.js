function tokenHeaders() {
    return { "Content-Type": "application/json", "Authorization": `Bearer ${getToken()}` };
}

const state = {
    calendar: null,
    team: [],
    rules: {},
    selectedDate: new Date().toISOString().slice(0, 10),
    selectedEmployeeId: "",
    recordsByDate: {},
    leavesByDate: {},
    dayDetailsByDate: {},
    loading: false,
    toolsLoaded: false,
};

function safeUser() {
    try { return typeof currentUser === "function" ? currentUser() : null; } catch { return null; }
}
function roleName() {
    const me = safeUser();
    return me?.hrms_role || me?.portal_role || me?.role || localStorage.getItem("hrms_role") || localStorage.getItem("role") || "Employee";
}
function canManagePanels() {
    return ["Super User", "Management Admin", "HR Director", "HR Manager", "HR Business Partner", "Senior Manager", "Employee Relations Manager", "HR Operations Specialist"].includes(roleName());
}
function isSuperUser() { return roleName() === "Super User"; }
function canReviewSelected() { return canManagePanels(); }
function canReviewRecord(record) {
    if (isSuperUser()) return true;
    const me = safeUser();
    const myId = String(me?.id || me?._id || "");
    return Boolean(myId && (record.manager_ids || []).map(String).includes(myId));
}

function localDate(value) {
    if (!value) return null;
    if (value instanceof Date) return value;
    const text = String(value);
    if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return new Date(`${text}T00:00:00`);
    const parsed = new Date(text);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
}
function dateKey(date) {
    const d = localDate(date) || new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
}
function todayKey() { return dateKey(new Date()); }
function monthKey(date) { return dateKey(date).slice(0, 7); }
function monthValue() {
    const input = document.getElementById("attendanceMonth");
    if (!input) return monthKey(new Date());
    if (!input.value) input.value = monthKey(state.selectedDate || new Date());
    return input.value;
}
function setMonthValue(value) {
    const input = document.getElementById("attendanceMonth");
    if (input) input.value = value;
}
function fmtDate(value) {
    const d = localDate(value);
    return d ? d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", year: "numeric" }) : "--";
}
function fmtTime(value) {
    const d = localDate(value);
    return d ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "--";
}
function worked(minutes) {
    minutes = Number(minutes || 0);
    return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}
function tagClass(tags = [], status = "") {
    const joined = [...(tags || []), status || ""].join(" ").toLowerCase();
    if (joined.includes("leave")) return "leave";
    if (joined.includes("absent")) return "absent";
    if (joined.includes("late")) return "late";
    if (joined.includes("overtime")) return "overtime";
    if (joined.includes("present") || joined.includes("full_day") || joined.includes("checked_in")) return "present";
    return "neutral";
}
function readable(value) { return String(value || "").replaceAll("_", " "); }
function badgeTags(tags = []) {
    return (tags || []).slice(0, 4).map(t => `<span class="pill ${tagClass([t])}">${escapeHTML(readable(t))}</span>`).join("");
}
function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}
function setLoading(isLoading) {
    state.loading = isLoading;
    document.querySelectorAll("#checkInBtn,#checkOutBtn,#refreshAttendanceBtn,#prevMonthBtn,#todayBtn,#nextMonthBtn").forEach(btn => btn.disabled = isLoading);
    const cal = document.getElementById("attendanceCalendar");
    if (cal) cal.classList.toggle("is-loading", isLoading);
}
async function api(path, options = {}) {
    try {
        const res = await fetch(path, { headers: tokenHeaders(), ...options });
        const text = await res.text();
        let data;
        try {
            data = text ? JSON.parse(text) : {};
        } catch {
            const message = res.status === 401
                ? "Your session expired. Please log in again."
                : `Server returned ${res.status || "an"} HTML/error response instead of JSON.`;
            toast(message, false);
            return { success: false, message };
        }
        if (!data.success && !data.warning) toast(data.message || "Request failed", false);
        if (data.warning) toast(data.message || "Please review", false, true);
        return data;
    } catch (err) {
        toast("Network or server error while loading attendance data", false);
        return { success: false, message: err.message };
    }
}

function buildIndexes(payload) {
    const recordsByDate = {};
    (payload.records || []).forEach(row => {
        const key = row.date;
        recordsByDate[key] = recordsByDate[key] || [];
        recordsByDate[key].push(row);
    });
    const leavesByDate = {};
    (payload.leaves || []).forEach(leave => {
        let d = localDate(leave.start_date);
        const end = localDate(leave.end_date || leave.start_date);
        while (d && end && d <= end) {
            const key = dateKey(d);
            leavesByDate[key] = leavesByDate[key] || [];
            leavesByDate[key].push(leave);
            d.setDate(d.getDate() + 1);
        }
    });
    state.recordsByDate = recordsByDate;
    state.leavesByDate = leavesByDate;
}

function currentVisibleRange(payload) {
    const mode = document.getElementById("attendanceViewMode")?.value || "monthly";
    const selected = localDate(state.selectedDate) || new Date();
    if (mode === "daily") return [dateKey(selected), dateKey(selected)];
    if (mode === "weekly") {
        const start = new Date(selected);
        const day = start.getDay() || 7;
        start.setDate(start.getDate() - day + 1);
        const end = new Date(start);
        end.setDate(start.getDate() + 6);
        return [dateKey(start), dateKey(end)];
    }
    return [payload.start, payload.end];
}
function daysBetween(start, end) {
    const days = [];
    let d = localDate(start);
    const e = localDate(end);
    while (d && e && d <= e) {
        days.push(new Date(d));
        d.setDate(d.getDate() + 1);
    }
    return days;
}
function bestDayClass(records, leaves) {
    if (records.length) {
        const priority = ["absent", "leave", "late", "overtime", "present"];
        const classes = records.map(r => tagClass(r.soft_tags, r.status));
        return priority.find(p => classes.includes(p)) || classes[0] || "neutral";
    }
    if (leaves.length) return tagClass([`leave_${leaves[0].status}`]);
    return "neutral";
}
function daySummary(records, leaves) {
    if (records.length) {
        const main = records[0];
        if (records.length > 1) return `${records.length} records`;
        return readable(main.status || "recorded");
    }
    if (leaves.length) return `Leave ${readable(leaves[0].status)}`;
    return "No log";
}
function renderCalendar(payload) {
    state.calendar = payload;
    buildIndexes(payload);
    const box = document.getElementById("attendanceCalendar");
    if (!box) return;
    const mode = document.getElementById("attendanceViewMode")?.value || "monthly";
    const [rangeStart, rangeEnd] = currentVisibleRange(payload);
    const days = daysBetween(rangeStart, rangeEnd);
    const weekdayHeader = mode === "monthly" ? ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(d => `<div class="calendar-weekday">${d}</div>`).join("") : "";
    let blanks = "";
    if (mode === "monthly" && days.length) {
        const first = days[0].getDay() || 7;
        blanks = Array.from({ length: first - 1 }).map(() => `<div class="calendar-day blank" aria-hidden="true"></div>`).join("");
    }
    const cells = days.map(d => {
        const key = dateKey(d);
        const records = state.recordsByDate[key] || [];
        const leaves = state.leavesByDate[key] || [];
        const main = records[0];
        const cls = bestDayClass(records, leaves);
        const selected = key === state.selectedDate ? "selected" : "";
        const isToday = key === todayKey() ? "today" : "";
        const tags = records.flatMap(r => r.soft_tags || []);
        if (!tags.length && leaves.length) tags.push(`leave_${leaves[0].status}`);
        const timeText = main ? `${fmtTime(main.check_in)} - ${fmtTime(main.check_out)}` : (leaves.length ? `${leaves.length} leave item${leaves.length > 1 ? "s" : ""}` : "Click for details");
        return `
            <button class="calendar-day ${cls} ${selected} ${isToday}" type="button" data-date="${key}">
                <span class="calendar-date"><strong>${d.getDate()}</strong><span>${d.toLocaleDateString([], { weekday: "short" })}</span></span>
                <p>${escapeHTML(main?.employee_name || leaves[0]?.employee_name || "")}</p>
                <h4>${escapeHTML(daySummary(records, leaves))}</h4>
                <small>${escapeHTML(timeText)}</small>
                <span class="tag-row">${badgeTags(tags)}</span>
            </button>`;
    }).join("");
    box.innerHTML = weekdayHeader + blanks + (cells || `<div class="empty-state">No attendance data for this range.</div>`);
    updateWidgets(payload);
    updateAttendanceAttention();
}

function updateWidgets(payload) {
    const records = payload.records || [];
    const leaves = payload.leaves || [];
    const today = records.find(r => r.date === todayKey());
    const todayLeaves = leaves.filter(l => l.start_date <= todayKey() && (l.end_date || l.start_date) >= todayKey());
    setText("todayStatus", today ? readable(today.status || "present") : (todayLeaves[0] ? `Leave ${readable(todayLeaves[0].status)}` : "No log"));
    setText("todayTimes", today ? `${fmtTime(today.check_in)} - ${fmtTime(today.check_out)}` : "Check in to start today");
    setText("todayWorked", today ? worked(today.worked_minutes) : "0h 0m");
    setText("todayWorkedNote", today?.check_out ? "Final recorded time" : (today?.check_in ? "Running day, checkout pending" : "Current recorded time"));
    const hasTag = (row, tag) => [...(row.soft_tags || []), ...(row.hard_tags || []), row.status || ""].join(" ").includes(tag);
    const present = records.filter(r => hasTag(r, "present") || hasTag(r, "full_day") || r.status === "present").length;
    const late = records.filter(r => hasTag(r, "late")).length;
    const overtime = records.filter(r => hasTag(r, "overtime")).length;
    const absent = records.filter(r => hasTag(r, "absent")).length;
    const leaveApproved = leaves.filter(l => l.status === "approved").length;
    const leavePending = leaves.filter(l => l.status === "pending").length;
    setText("presentCount", String(present));
    setText("lateOvertimeCount", `${late} / ${overtime}`);
    setText("absentCount", String(absent));
    setText("leaveCount", String(leaveApproved + leavePending));
    setText("leaveNote", `${leaveApproved} approved · ${leavePending} pending`);
    setText("pendingLeaveCount", String(leavePending));
    const [s, e] = currentVisibleRange(payload);
    setText("calendarRangeLabel", s === e ? fmtDate(s) : `${fmtDate(s)} → ${fmtDate(e)}`);
}

function updateAttendanceAttention() {
    const pendingLeaves = Number(document.getElementById("pendingLeaveCount")?.textContent || 0);
    const pendingReviews = Number(document.getElementById("pendingReviewCount")?.textContent || 0);
    const correctionSummary = document.getElementById("correctionSummary")?.textContent || "";
    const meetingSummary = document.getElementById("meetingSummary")?.textContent || "";
    const pendingCorrections = Number((correctionSummary.match(/\d+/) || [0])[0]);
    const scheduledMeetings = Number((meetingSummary.match(/\d+/) || [0])[0]);
    const total = pendingLeaves + pendingReviews + pendingCorrections + scheduledMeetings;
    setText("attendanceAttentionCount", String(total));
    setText("attendanceStatusSummary", `${total} need attention`);
}

function renderSelectedDay(detailRecords = null) {
    const date = state.selectedDate || todayKey();
    const records = detailRecords || state.dayDetailsByDate[date] || [];
    const leaves = state.leavesByDate[date] || [];
    setText("selectedDayTitle", fmtDate(date));
    setText("selectedDaySubtitle", `${records.length} attendance record${records.length === 1 ? "" : "s"} · ${leaves.length} leave item${leaves.length === 1 ? "" : "s"}`);
    const box = document.getElementById("selectedDayDetails");
    const actions = document.getElementById("selectedDayActions");
    const meetingBtn = document.getElementById("scheduleMeetingForSelectedBtn");
    if (!box) return;
    const recordHtml = records.map(r => `
        <div class="detail-card ${tagClass(r.soft_tags, r.status)}">
            <div class="split"><strong>${escapeHTML(r.employee_name || "Employee")}</strong><span class="pill ${tagClass(r.soft_tags, r.status)}">${escapeHTML(readable(r.status))}</span></div>
            <p><b>Check-in:</b> ${fmtTime(r.check_in)} &nbsp; <b>Checkout:</b> ${fmtTime(r.check_out)}</p>
            <p><b>Worked:</b> ${worked(r.worked_minutes)} &nbsp; <b>Manager status:</b> ${escapeHTML(readable(r.manager_status || "normal"))}</p>
            <div class="tag-row">${badgeTags([...(r.soft_tags || []), ...(r.hard_tags || [])]) || `<span class="pill neutral">No tags</span>`}</div>
            ${canReviewRecord(r) && r.id ? `<div class="action-row detail-actions"><button class="btn tiny" data-review-id="${r.id}" data-review-action="confirm_present">Confirm Present</button><button class="btn tiny secondary" data-review-id="${r.id}" data-review-action="excuse_late">Excuse</button><button class="btn tiny danger" data-review-id="${r.id}" data-review-action="confirm_absent">Confirm Absent</button><button class="btn tiny secondary" data-edit-time-id="${r.id}" data-current-in="${escapeHTML(r.check_in || "")}" data-current-out="${escapeHTML(r.check_out || "")}">Edit Times</button><button class="btn tiny danger" data-reset-time-id="${r.id}">Reset Times</button></div>` : ""}
        </div>`).join("");
    const leaveHtml = leaves.map(l => `
        <div class="detail-card leave">
            <div class="split"><strong>${escapeHTML(readable(l.leave_type))}</strong><span class="pill ${escapeHTML(l.status)}">${escapeHTML(readable(l.status))}</span></div>
            <p>${escapeHTML(l.start_date)} to ${escapeHTML(l.end_date)} · ${Number(l.days || 1)} day(s)</p>
            <p>${escapeHTML(l.reason || "No reason added")}</p>
            ${canReviewSelected() && l.status === "pending" ? `<div class="action-row detail-actions"><button class="btn tiny" data-leave-id="${l.id}" data-leave-action="approve">Approve</button><button class="btn tiny danger" data-leave-id="${l.id}" data-leave-action="reject">Reject</button></div>` : ""}
        </div>`).join("");
    box.classList.toggle("empty-state", !records.length && !leaves.length);
    box.innerHTML = recordHtml + leaveHtml || "No attendance or leave record found for this day. You can request leave or submit a correction for this date.";
    if (actions) actions.hidden = false;
    if (meetingBtn) meetingBtn.hidden = !canManagePanels();
}

function selectDay(date) {
    state.selectedDate = date;
    setMonthValue(monthKey(date));
    document.querySelectorAll(".calendar-day.selected").forEach(el => el.classList.remove("selected"));
    document.querySelector(`.calendar-day[data-date="${date}"]`)?.classList.add("selected");
    openAttendanceDay();
}

async function loadSelectedDayDetails(force = false) {
    const date = state.selectedDate || todayKey();
    const box = document.getElementById("selectedDayDetails");
    if (box) {
        box.classList.add("empty-state");
        box.innerHTML = "Loading day details...";
    }
    if (!force && state.dayDetailsByDate[date]) {
        renderSelectedDay(state.dayDetailsByDate[date]);
        return;
    }
    const employee = state.selectedEmployeeId ? `&employee_id=${encodeURIComponent(state.selectedEmployeeId)}` : "";
    const data = await api(`/api/hrms/attendance?start=${encodeURIComponent(date)}&end=${encodeURIComponent(date)}${employee}`);
    state.dayDetailsByDate[date] = data.success ? (data.data?.logs || []) : [];
    renderSelectedDay(state.dayDetailsByDate[date]);
}

function openAttendanceDay() {
    const modal = document.getElementById("attendanceDayModal");
    if (!modal) return;
    modal.hidden = false;
    document.body.classList.add("modal-open");
    renderSelectedDay([]);
    loadSelectedDayDetails();
}

function closeAttendanceDay() {
    const modal = document.getElementById("attendanceDayModal");
    if (modal) modal.hidden = true;
    document.body.classList.remove("modal-open");
}
function jumpPeriod(delta) {
    const mode = document.getElementById("attendanceViewMode")?.value || "monthly";
    const d = localDate(state.selectedDate) || new Date();
    if (mode === "daily") d.setDate(d.getDate() + delta);
    else if (mode === "weekly") d.setDate(d.getDate() + (delta * 7));
    else d.setMonth(d.getMonth() + delta);
    state.selectedDate = dateKey(d);
    setMonthValue(monthKey(d));
    loadAttendance();
}
function prefillLeaveFromSelected() {
    openAttendanceTools();
    const form = document.getElementById("leaveRequestForm");
    if (!form) return;
    form.elements.start_date.value = state.selectedDate;
    form.elements.end_date.value = state.selectedDate;
    form.elements.reason.focus();
}
function prefillCorrectionFromSelected() {
    openAttendanceTools();
    const form = document.getElementById("correctionForm");
    if (!form) return;
    form.elements.date.value = state.selectedDate;
    form.elements.reason.focus();
}
function prefillMeetingFromSelected() {
    openAttendanceTools();
    const form = document.getElementById("meetingForm");
    if (!form) return;
    const records = state.recordsByDate[state.selectedDate] || [];
    const leaves = state.leavesByDate[state.selectedDate] || [];
    const employeeId = records[0]?.employee_id || leaves[0]?.employee_id || state.selectedEmployeeId || "";
    if (employeeId) form.elements.employee_id.value = employeeId;
    form.elements.meeting_date.value = state.selectedDate;
    form.elements.reason.value = form.elements.reason.value || "Attendance follow-up";
    form.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function loadAttendance() {
    if (!requireAuth()) return;
    setLoading(true);
    monthValue();
    state.selectedEmployeeId = document.getElementById("attendanceEmployeeSelect")?.value || sessionStorage.getItem("attendanceEmployeeParam") || "";
    state.dayDetailsByDate = {};
    const url = `/api/hrms/attendance/calendar?summary_only=1&month=${encodeURIComponent(monthValue())}${state.selectedEmployeeId ? `&employee_id=${encodeURIComponent(state.selectedEmployeeId)}` : ""}`;
    const data = await api(url);
    if (data.success) renderCalendar(data.data);
    if (state.toolsLoaded) await loadAttendanceTools(true);
    setLoading(false);
}
async function checkIn() {
    const data = await api("/api/hrms/attendance/check-in", { method: "POST", body: JSON.stringify({}) });
    toast(data.message || "Check-in updated", data.success, data.warning);
    if (data.success || data.warning) loadAttendance();
}
async function checkOut() {
    const data = await api("/api/hrms/attendance/check-out", { method: "POST", body: JSON.stringify({}) });
    toast(data.message || "Checkout updated", data.success, data.warning);
    if (data.success || data.warning) loadAttendance();
}

async function loadLeaves() {
    const mine = await api("/api/hrms/leave/my");
    const list = document.getElementById("myLeaveList");
    const leaves = mine.data?.leaves || [];
    const pending = leaves.filter(l => l.status === "pending").length;
    setText("pendingLeaveCount", String(Math.max(Number(document.getElementById("pendingLeaveCount")?.textContent || 0), pending)));
    setText("myLeaveSummary", `${pending} pending · ${leaves.filter(l => l.status === "approved").length} approved`);
    if (list) list.innerHTML = leaves.map(l => `<div class="mini-item clickable-row" data-leave-date="${escapeHTML(l.start_date)}"><span><strong>${escapeHTML(readable(l.leave_type))}</strong><br>${escapeHTML(l.start_date)} to ${escapeHTML(l.end_date)}<br>${escapeHTML(l.reason || "")}</span><strong class="pill ${escapeHTML(l.status)}">${escapeHTML(readable(l.status))}</strong></div>`).join("") || `<div class="mini-item"><span>No leave requests yet</span><strong>0</strong></div>`;
}
async function submitLeave(e) {
    e.preventDefault();
    const form = e.currentTarget;
    const payload = Object.fromEntries(new FormData(form).entries());
    if (!payload.end_date) payload.end_date = payload.start_date;
    const data = await api("/api/hrms/leave/request", { method: "POST", body: JSON.stringify(payload) });
    toast(data.message || "Leave requested", data.success, data.warning);
    if (data.success) { form.reset(); loadAttendance(); }
}

async function loadTeamData() {
    document.getElementById("managerAttendancePanels")?.removeAttribute("hidden");
    document.getElementById("reviewMeetingPanels")?.removeAttribute("hidden");
    const data = await api("/api/hrms/attendance/team");
    if (!data.success) return;
    state.team = data.data.employees || [];
    const empSelect = document.getElementById("attendanceEmployeeSelect");
    const meetingSelect = document.getElementById("meetingEmployeeSelect");
    const currentValue = empSelect?.value || sessionStorage.getItem("attendanceEmployeeParam") || "";
    const options = `<option value="">My / scoped calendar</option>` + state.team.map(e => `<option value="${e.id}">${escapeHTML(e.name || e.email)} - ${escapeHTML(e.department || "")}</option>`).join("");
    if (empSelect) {
        empSelect.innerHTML = options;
        empSelect.value = currentValue;
    }
    if (meetingSelect) meetingSelect.innerHTML = `<option value="">Select employee</option>` + state.team.map(e => `<option value="${e.id}">${escapeHTML(e.name || e.email)}</option>`).join("");
    const todayLogs = data.data.logs || [];
    const todayByEmployee = {};
    todayLogs.filter(l => l.date === todayKey()).forEach(l => todayByEmployee[l.employee_id] = l);
    const teamBox = document.getElementById("teamEmployeeList");
    if (teamBox) teamBox.innerHTML = state.team.map(e => {
        const log = todayByEmployee[e.id];
        const cls = tagClass(log?.soft_tags || [], log?.status || "");
        return `<div class="mini-item team-row"><label class="check-row"><input type="checkbox" class="team-user-check" value="${e.id}"> <span><strong>${escapeHTML(e.name || e.email)}</strong><br>${escapeHTML(e.department || "Unassigned")} · ${escapeHTML(e.designation || "")}</span></label><span class="action-row"><span class="pill ${cls}">${escapeHTML(readable(log?.status || "no log"))}</span><button class="btn tiny" data-view-employee="${e.id}">Calendar</button><a class="btn tiny secondary" href="/messages?employee=${e.id}">Message</a></span></div>`;
    }).join("") || `<div class="mini-item"><span>No team employees found</span></div>`;
    renderLeaveApprovals(data.data.pending_leaves || []);
    renderReviews(data.data.pending_reviews || []);
    setText("pendingReviewCount", String((data.data.pending_reviews || []).length));
    await loadMeetings();
    await loadCorrections();
}
function viewEmployeeCalendar(id) {
    const select = document.getElementById("attendanceEmployeeSelect");
    if (select) select.value = id;
    sessionStorage.setItem("attendanceEmployeeParam", id || "");
    state.selectedEmployeeId = id || "";
    loadAttendance();
}
function renderLeaveApprovals(leaves) {
    const box = document.getElementById("leaveApprovalList");
    setText("leaveApprovalSummary", `${leaves.length} pending`);
    if (!box) return;
    box.innerHTML = leaves.map(l => `<div class="mini-item clickable-row" data-leave-date="${escapeHTML(l.start_date)}"><label class="check-row"><input type="checkbox" class="leave-check" value="${l.id}"> <span><strong>${escapeHTML(l.employee_name)}</strong><br>${escapeHTML(readable(l.leave_type))}: ${escapeHTML(l.start_date)} to ${escapeHTML(l.end_date)}<br>${escapeHTML(l.reason || "")}</span></label><span class="action-row"><button class="btn tiny" data-leave-id="${l.id}" data-leave-action="approve">Approve</button><button class="btn tiny danger" data-leave-id="${l.id}" data-leave-action="reject">Reject</button></span></div>`).join("") || `<div class="mini-item"><span>No pending leave approvals</span></div>`;
}
async function reviewLeave(id, action) {
    const note = prompt("Manager note", "") || "";
    const data = await api(`/api/hrms/leave/${id}/${action}`, { method: "POST", body: JSON.stringify({ note }) });
    toast(data.message || "Leave updated", data.success, data.warning);
    if (data.success || data.warning) loadAttendance();
}
function renderReviews(rows) {
    const box = document.getElementById("attendanceReviewList");
    setText("reviewSummary", `${rows.length} pending`);
    if (!box) return;
    const actionable = rows.filter(canReviewRecord);
    box.innerHTML = actionable.map(r => `<div class="mini-item clickable-row" data-record-date="${escapeHTML(r.date)}"><label class="check-row"><input type="checkbox" class="review-check" value="${r.id}"> <span><strong>${escapeHTML(r.employee_name)}</strong><br>${escapeHTML(r.date)} · ${badgeTags(r.soft_tags)}<br>${escapeHTML(readable(r.status))}</span></label><span class="action-row"><button class="btn tiny" data-review-id="${r.id}" data-review-action="confirm_present">Confirm</button><button class="btn tiny secondary" data-review-id="${r.id}" data-review-action="excuse_late">Excuse</button><button class="btn tiny danger" data-review-id="${r.id}" data-review-action="confirm_absent">Absent</button><button class="btn tiny secondary" data-edit-time-id="${r.id}" data-current-in="${escapeHTML(r.check_in || "")}" data-current-out="${escapeHTML(r.check_out || "")}">Edit Times</button></span></div>`).join("") || `<div class="mini-item"><span>No pending abnormality reviews for your assigned employees</span></div>`;
}
async function reviewAttendance(id, action) {
    const note = prompt("Review note", "") || "";
    const endpoint = action.startsWith("excuse") ? "excuse" : "confirm";
    const data = await api(`/api/hrms/attendance/${id}/${endpoint}`, { method: "POST", body: JSON.stringify({ action, note }) });
    toast(data.message || "Review updated", data.success, data.warning);
    if (data.success || data.warning) loadAttendance();
}

function toDatetimeLocal(value) {
    const d = localDate(value);
    if (!d) return "";
    const pad = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
async function editAttendanceTimes(id, currentIn, currentOut) {
    const checkIn = prompt("Check-in time (YYYY-MM-DDTHH:mm). Leave blank to clear.", toDatetimeLocal(currentIn));
    if (checkIn === null) return;
    const checkOut = prompt("Checkout time (YYYY-MM-DDTHH:mm). Leave blank to clear.", toDatetimeLocal(currentOut));
    if (checkOut === null) return;
    const note = prompt("Reason for time change", "Manager adjusted attendance time") || "Manager adjusted attendance time";
    const data = await api(`/api/hrms/attendance/${id}/override`, { method: "POST", body: JSON.stringify({ action: "confirm_present", note, overrides: { check_in: checkIn, check_out: checkOut } }) });
    toast(data.message || "Attendance times updated", data.success, data.warning);
    if (data.success || data.warning) loadAttendance();
}
async function resetAttendanceTimes(id) {
    if (!confirm("Reset both check-in and checkout for this attendance record?")) return;
    const note = prompt("Reason for reset", "Manager reset attendance times") || "Manager reset attendance times";
    const data = await api(`/api/hrms/attendance/${id}/override`, { method: "POST", body: JSON.stringify({ action: "confirm_absent", note, overrides: { check_in: "", check_out: "" } }) });
    toast(data.message || "Attendance times reset", data.success, data.warning);
    if (data.success || data.warning) loadAttendance();
}

async function submitMeeting(e) {
    e.preventDefault();
    const form = e.currentTarget;
    const payload = Object.fromEntries(new FormData(form).entries());
    const data = await api("/api/hrms/attendance/meeting", { method: "POST", body: JSON.stringify(payload) });
    toast(data.message || "Meeting scheduled", data.success, data.warning);
    if (data.success) { form.reset(); loadMeetings(); }
}
async function loadMeetings() {
    const data = await api("/api/hrms/attendance/meetings/my");
    const box = document.getElementById("meetingList");
    if (!box || !data.success) return;
    const rows = data.data.meetings || [];
    setText("meetingSummary", `${rows.filter(m => m.status === "scheduled").length} scheduled`);
    box.innerHTML = rows.map(m => `<div class="mini-item"><span><strong>${escapeHTML(m.employee_name || "Employee")}</strong><br>${escapeHTML(m.meeting_date)} ${escapeHTML(m.meeting_time)}<br>${escapeHTML(m.reason || "")}</span><strong class="pill ${escapeHTML(m.status)}">${escapeHTML(readable(m.status))}</strong></div>`).join("") || `<div class="mini-item"><span>No attendance meetings</span></div>`;
}
async function submitCorrection(e) {
    e.preventDefault();
    const form = e.currentTarget;
    const payload = Object.fromEntries(new FormData(form).entries());
    const data = await api("/api/hrms/attendance/correction", { method: "POST", body: JSON.stringify(payload) });
    toast(data.message || "Correction requested", data.success, data.warning);
    if (data.success) { form.reset(); loadCorrections(); }
}
async function loadCorrections() {
    const data = await api("/api/hrms/attendance/corrections");
    const box = document.getElementById("correctionList");
    if (!box || !data.success) return;
    const rows = data.data.corrections || [];
    setText("correctionSummary", `${rows.filter(c => c.status === "pending").length} pending`);
    box.innerHTML = rows.map(c => `<div class="mini-item clickable-row" data-record-date="${escapeHTML(c.date)}"><span>${escapeHTML(c.date)} · ${escapeHTML(c.reason || "")}</span><strong class="pill ${escapeHTML(c.status)}">${escapeHTML(readable(c.status))}</strong></div>`).join("") || `<div class="mini-item"><span>No correction requests</span></div>`;
}
async function loadRules() {
    document.getElementById("attendanceRulesPanel")?.removeAttribute("hidden");
    const data = await api("/api/hrms/attendance/rules");
    if (!data.success) return;
    state.rules = data.data.rules || {};
    const form = document.getElementById("rulesForm");
    if (!form) return;
    Object.entries(state.rules).forEach(([k, v]) => {
        if (form.elements[k]) form.elements[k].value = Array.isArray(v) ? v.join(",") : v;
    });
}
async function saveRules(e) {
    e.preventDefault();
    const payload = Object.fromEntries(new FormData(e.currentTarget).entries());
    payload.working_days = (payload.working_days || "").split(",").map(x => x.trim()).filter(Boolean);
    payload.holidays = (payload.holidays || "").split(",").map(x => x.trim()).filter(Boolean);
    ["minimum_full_day_minutes", "minimum_half_day_minutes", "overtime_after_minutes"].forEach(k => payload[k] = Number(payload[k] || 0));
    const data = await api("/api/hrms/attendance/rules", { method: "POST", body: JSON.stringify(payload) });
    toast(data.message || "Rules saved", data.success, data.warning);
    if (data.success) loadAttendance();
}
async function repairManagers() {
    const data = await api("/api/hrms/managers/repair", { method: "POST", body: JSON.stringify({}) });
    toast(data.message || "Managers checked", data.success, data.warning);
    if (data.success || data.warning) loadAttendance();
}

async function loadAttendanceTools(force = false) {
    if (state.toolsLoaded && !force) return;
    await loadLeaves();
    await loadCorrections();
    if (canManagePanels()) await loadTeamData();
    if (isSuperUser()) await loadRules();
    state.toolsLoaded = true;
    updateAttendanceAttention();
}

function openAttendanceTools() {
    const modal = document.getElementById("attendanceToolsModal");
    if (!modal) return;
    modal.hidden = false;
    document.body.classList.add("modal-open");
    loadAttendanceTools();
}

function closeAttendanceTools() {
    const modal = document.getElementById("attendanceToolsModal");
    if (modal) modal.hidden = true;
    document.body.classList.remove("modal-open");
}


function checkedValues(selector) { return Array.from(document.querySelectorAll(selector + ":checked")).map(el => el.value); }
async function bulkReviewAttendance(action) {
    const ids = checkedValues(".review-check");
    if (!ids.length) return toast("Select at least one anomaly first", false, true);
    const note = prompt("Bulk review note", "Bulk manager review") || "Bulk manager review";
    const data = await api("/api/hrms/attendance/bulk-review", { method: "POST", body: JSON.stringify({ attendance_ids: ids, action, note }) });
    toast(`${data.data?.updated_count || 0} attendance record(s) updated`, data.success, data.warning);
    if (data.success || data.warning) loadAttendance();
}
async function bulkReviewLeaves(action) {
    const ids = checkedValues(".leave-check");
    if (!ids.length) return toast("Select at least one leave request first", false, true);
    const note = prompt("Bulk leave note", "Bulk leave review") || "Bulk leave review";
    const data = await api("/api/hrms/leave/bulk-review", { method: "POST", body: JSON.stringify({ leave_ids: ids, action, note }) });
    toast(`${data.data?.updated_count || 0} leave request(s) updated`, data.success, data.warning);
    if (data.success || data.warning) loadAttendance();
}
async function bulkScheduleMeetings() {
    const ids = checkedValues(".team-user-check");
    if (!ids.length) return toast("Select at least one team user first", false, true);
    const form = document.getElementById("meetingForm");
    const payload = form ? Object.fromEntries(new FormData(form).entries()) : {};
    payload.employee_ids = ids;
    payload.meeting_date = payload.meeting_date || state.selectedDate || todayKey();
    payload.meeting_time = payload.meeting_time || "10:00";
    payload.reason = payload.reason || "Attendance follow-up";
    const data = await api("/api/hrms/attendance/meeting/bulk", { method: "POST", body: JSON.stringify(payload) });
    toast(`${data.data?.created_count || 0} meeting(s) scheduled`, data.success, data.warning);
    if (data.success || data.warning) loadMeetings();
}

function initAttendancePage() {
    const params = new URLSearchParams(window.location.search);
    const employeeParam = params.get("employee");
    if (employeeParam) sessionStorage.setItem("attendanceEmployeeParam", employeeParam);
    state.selectedEmployeeId = employeeParam || sessionStorage.getItem("attendanceEmployeeParam") || "";
    state.selectedDate = params.get("date") || todayKey();
    setMonthValue(monthKey(state.selectedDate));
    document.getElementById("checkInBtn")?.addEventListener("click", checkIn);
    document.getElementById("checkOutBtn")?.addEventListener("click", checkOut);
    document.getElementById("refreshAttendanceBtn")?.addEventListener("click", loadAttendance);
    document.getElementById("openAttendanceToolsBtn")?.addEventListener("click", openAttendanceTools);
    document.querySelectorAll("[data-close-attendance-tools]").forEach(el => el.addEventListener("click", closeAttendanceTools));
    document.querySelectorAll("[data-close-attendance-day]").forEach(el => el.addEventListener("click", closeAttendanceDay));
    document.getElementById("prevMonthBtn")?.addEventListener("click", () => jumpPeriod(-1));
    document.getElementById("nextMonthBtn")?.addEventListener("click", () => jumpPeriod(1));
    document.getElementById("todayBtn")?.addEventListener("click", () => { state.selectedDate = todayKey(); setMonthValue(monthKey(state.selectedDate)); loadAttendance(); });
    document.getElementById("attendanceViewMode")?.addEventListener("change", loadAttendance);
    document.getElementById("attendanceMonth")?.addEventListener("change", e => { state.selectedDate = `${e.target.value}-01`; loadAttendance(); });
    document.getElementById("attendanceEmployeeSelect")?.addEventListener("change", e => { sessionStorage.setItem("attendanceEmployeeParam", e.target.value || ""); state.selectedEmployeeId = e.target.value || ""; loadAttendance(); });
    document.getElementById("leaveRequestForm")?.addEventListener("submit", submitLeave);
    document.getElementById("meetingForm")?.addEventListener("submit", submitMeeting);
    document.getElementById("correctionForm")?.addEventListener("submit", submitCorrection);
    document.getElementById("rulesForm")?.addEventListener("submit", saveRules);
    document.getElementById("repairManagersBtn")?.addEventListener("click", repairManagers);
    document.getElementById("bulkConfirmReviewsBtn")?.addEventListener("click", () => bulkReviewAttendance("confirm_present"));
    document.getElementById("bulkExcuseReviewsBtn")?.addEventListener("click", () => bulkReviewAttendance("excuse_late"));
    document.getElementById("bulkAbsentReviewsBtn")?.addEventListener("click", () => bulkReviewAttendance("confirm_absent"));
    document.getElementById("bulkApproveLeavesBtn")?.addEventListener("click", () => bulkReviewLeaves("approve"));
    document.getElementById("bulkRejectLeavesBtn")?.addEventListener("click", () => bulkReviewLeaves("reject"));
    document.getElementById("bulkMeetingBtn")?.addEventListener("click", bulkScheduleMeetings);
    document.getElementById("requestLeaveForSelectedBtn")?.addEventListener("click", prefillLeaveFromSelected);
    document.getElementById("requestCorrectionForSelectedBtn")?.addEventListener("click", prefillCorrectionFromSelected);
    document.getElementById("scheduleMeetingForSelectedBtn")?.addEventListener("click", prefillMeetingFromSelected);

    document.addEventListener("click", e => {
        const day = e.target.closest(".calendar-day[data-date]");
        if (day) selectDay(day.dataset.date);
        const viewEmployee = e.target.closest("[data-view-employee]");
        if (viewEmployee) viewEmployeeCalendar(viewEmployee.dataset.viewEmployee);
        const leaveBtn = e.target.closest("[data-leave-id][data-leave-action]");
        if (leaveBtn) reviewLeave(leaveBtn.dataset.leaveId, leaveBtn.dataset.leaveAction);
        const reviewBtn = e.target.closest("[data-review-id][data-review-action]");
        if (reviewBtn) reviewAttendance(reviewBtn.dataset.reviewId, reviewBtn.dataset.reviewAction);
        const editBtn = e.target.closest("[data-edit-time-id]");
        if (editBtn) editAttendanceTimes(editBtn.dataset.editTimeId, editBtn.dataset.currentIn, editBtn.dataset.currentOut);
        const resetBtn = e.target.closest("[data-reset-time-id]");
        if (resetBtn) resetAttendanceTimes(resetBtn.dataset.resetTimeId);
        const leaveRow = e.target.closest("[data-leave-date]");
        if (leaveRow && !e.target.closest("button")) selectDay(leaveRow.dataset.leaveDate);
        const recordRow = e.target.closest("[data-record-date]");
        if (recordRow && !e.target.closest("button")) selectDay(recordRow.dataset.recordDate);
        const widget = e.target.closest("[data-widget='today']");
        if (widget) selectDay(todayKey());
    });
    loadAttendance();
}

initAttendancePage();
