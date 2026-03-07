import { useState, useEffect } from "react";
import { channels as channelsApi } from "../api/client";

export default function ChannelList({ server, activeChannel, onSelect }) {
  const [channelList, setChannelList] = useState([]);

  useEffect(() => {
    if (!server) return;
    channelsApi
      .list(server.id)
      .then((data) => setChannelList(data.channels || []))
      .catch(() => {});
  }, [server]);

  if (!server) {
    return (
      <div className="w-60 bg-cyber-panel/50 border-r border-cyber-border/40 flex flex-col items-center justify-center gap-3">
        <div className="w-12 h-12 rounded-xl bg-cyber-border/20 flex items-center justify-center text-cyber-muted/40 text-2xl">
          ◇
        </div>
        <p className="text-cyber-muted/60 text-xs font-display uppercase tracking-widest">Select a server</p>
      </div>
    );
  }

  const voiceChannels = channelList.filter((c) => c.type === "voice");
  const textChannels = channelList.filter((c) => c.type === "text");

  return (
    <div className="w-60 bg-cyber-panel/50 border-r border-cyber-border/40 flex flex-col">
      {/* Server name header */}
      <div className="px-4 h-12 flex items-center border-b border-cyber-border/40 bg-cyber-surface/30">
        <h2 className="text-sm font-display font-bold text-cyber-text uppercase tracking-wider truncate">
          {server.name}
        </h2>
        <span className="ml-auto text-[10px] text-cyber-muted bg-cyber-bg/40 px-2 py-0.5 rounded-full">
          {channelList.length}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto py-3">
        {/* Text channels */}
        {textChannels.length > 0 && (
          <div className="mb-4">
            <p className="px-4 text-[10px] text-cyber-muted/70 uppercase tracking-[0.2em] font-display font-semibold mb-2 flex items-center gap-2">
              <span className="h-px flex-1 bg-cyber-border/30" />
              Text
              <span className="h-px flex-1 bg-cyber-border/30" />
            </p>
            {textChannels.map((ch) => (
              <ChannelItem
                key={ch.id}
                channel={ch}
                active={activeChannel?.id === ch.id}
                onSelect={onSelect}
                icon="#"
              />
            ))}
          </div>
        )}

        {/* Voice channels */}
        {voiceChannels.length > 0 && (
          <div>
            <p className="px-4 text-[10px] text-cyber-muted/70 uppercase tracking-[0.2em] font-display font-semibold mb-2 flex items-center gap-2">
              <span className="h-px flex-1 bg-cyber-border/30" />
              Voice
              <span className="h-px flex-1 bg-cyber-border/30" />
            </p>
            {voiceChannels.map((ch) => (
              <ChannelItem
                key={ch.id}
                channel={ch}
                active={activeChannel?.id === ch.id}
                onSelect={onSelect}
                icon="◈"
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ChannelItem({ channel, active, onSelect, icon }) {
  return (
    <button
      onClick={() => onSelect(channel)}
      className={`w-full px-3 py-1.5 mx-0 flex items-center gap-2.5 text-sm transition-all duration-200 cursor-pointer
                  group rounded-none
                  ${
                    active
                      ? "bg-neon-cyan/8 text-neon-cyan border-l-2 border-neon-cyan pl-[10px]"
                      : "text-cyber-muted hover:text-cyber-text hover:bg-cyber-hover/50 border-l-2 border-transparent pl-[10px]"
                  }`}
    >
      <span className={`text-xs ${active ? "text-neon-cyan/80" : "text-cyber-muted/40 group-hover:text-cyber-muted/70"} transition-colors`}>
        {icon}
      </span>
      <span className="truncate font-display font-medium text-[13px]">{channel.name}</span>
      {channel.user_limit > 0 && (
        <span className="ml-auto text-[9px] text-cyber-muted/50 tabular-nums">{channel.user_limit}</span>
      )}
    </button>
  );
}
