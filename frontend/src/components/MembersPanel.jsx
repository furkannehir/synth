import { useAuth } from "../context/AuthContext";
import { useServerPresence } from "../context/ServerPresenceContext";

export default function MembersPanel({ server }) {
  const { user: currentUser } = useAuth();
  const { members, connected } = useServerPresence();

  const online = members.filter((m) => m.is_online);
  const offline = members.filter((m) => !m.is_online);

  if (!server) {
    return (
      <div className="w-56 bg-cyber-panel/40 border-l border-cyber-border/40 flex flex-col
                      items-center justify-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-cyber-border/15 flex items-center justify-center
                        text-cyber-muted/30 text-xl">
          ◫
        </div>
        <p className="text-cyber-muted/40 text-[10px] font-display uppercase tracking-widest">
          No server
        </p>
      </div>
    );
  }

  return (
    <div className="w-56 bg-cyber-panel/40 border-l border-cyber-border/40 flex flex-col">
      {/* Header */}
      <div className="px-4 h-12 flex items-center border-b border-cyber-border/40 bg-cyber-surface/30 gap-2">
        <span
          className={`w-1.5 h-1.5 rounded-full transition-colors duration-500
                      ${connected ? "bg-neon-green animate-pulse" : "bg-cyber-muted/40"}`}
        />
        <h3 className="text-[11px] font-display font-bold text-cyber-text/80 uppercase tracking-[0.2em]">
          Members
        </h3>
        <span className="ml-auto text-[10px] text-cyber-muted bg-cyber-bg/40 px-2 py-0.5 rounded-full tabular-nums">
          {members.length}
        </span>
      </div>

      {/* Reconnecting banner */}
      {!connected && members.length > 0 && (
        <div className="px-3 py-1.5 bg-neon-red/5 border-b border-neon-red/20 text-[9px]
                        text-neon-red/70 font-display uppercase tracking-wider text-center">
          ⟳ Reconnecting…
        </div>
      )}

      {/* Scrollable member list */}
      <div className="flex-1 overflow-y-auto py-3 space-y-4">
        {/* Online */}
        {online.length > 0 && (
          <section>
            <p className="px-4 text-[9px] font-display font-bold uppercase tracking-[0.25em]
                          text-neon-green/60 mb-2">
              Online — {online.length}
            </p>
            {online.map((m) => (
              <MemberRow
                key={m.id}
                member={m}
                isOnline={true}
                isYou={m.id === currentUser?.id}
              />
            ))}
          </section>
        )}

        {/* Offline */}
        {offline.length > 0 && (
          <section>
            <p className="px-4 text-[9px] font-display font-bold uppercase tracking-[0.25em]
                          text-cyber-muted/50 mb-2">
              Offline — {offline.length}
            </p>
            {offline.map((m) => (
              <MemberRow
                key={m.id}
                member={m}
                isOnline={false}
                isYou={m.id === currentUser?.id}
              />
            ))}
          </section>
        )}

        {members.length === 0 && (
          <p className="px-4 text-[10px] text-cyber-muted/40 font-display uppercase tracking-widest">
            {connected ? "No members yet" : "Connecting…"}
          </p>
        )}
      </div>
    </div>
  );
}

function MemberRow({ member, isOnline, isYou }) {
  const initials = (member.username || "?").slice(0, 2).toUpperCase();

  return (
    <div
      className={`flex items-center gap-2.5 px-3 py-1.5 mx-1 rounded-lg
                  transition-all duration-200 group
                  ${isOnline ? "hover:bg-cyber-hover/40" : "hover:bg-cyber-hover/20 opacity-60"}`}
    >
      {/* Avatar */}
      <div className="relative flex-shrink-0">
        <div
          className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px]
                      font-display font-bold transition-all duration-300
                      ${isOnline
                        ? "bg-gradient-to-br from-neon-cyan/25 to-neon-cyan/10 text-neon-cyan border border-neon-cyan/20"
                        : "bg-gradient-to-br from-cyber-muted/15 to-cyber-muted/5 text-cyber-muted/60 border border-cyber-border/20"
                      }`}
        >
          {initials}
        </div>
        {/* Status dot */}
        <span
          className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-cyber-panel
                      ${isOnline ? "bg-neon-green" : "bg-cyber-muted/40"}`}
        />
      </div>

      {/* Name */}
      <div className="flex-1 min-w-0">
        <p
          className={`text-[12px] font-display font-medium truncate leading-tight
                      ${isOnline ? "text-cyber-text" : "text-cyber-muted/60"}`}
        >
          {member.username}
          {isYou && (
            <span className="ml-1 text-[9px] text-neon-cyan/60 font-normal">you</span>
          )}
        </p>
        {isOnline && (
          <p className="text-[9px] text-neon-green/60 font-display uppercase tracking-wider leading-tight">
            online
          </p>
        )}
      </div>
    </div>
  );
}
