from marshmallow import Schema, fields


# ── Common ──────────────────────────────────────────────────

class ErrorSchema(Schema):
    error = fields.String(metadata={"description": "Error message"})


class MessageSchema(Schema):
    message = fields.String(metadata={"description": "Success message"})


# ── Auth ────────────────────────────────────────────────────

class RegisterSchema(Schema):
    username = fields.String(required=True, metadata={"description": "Username (min 3 chars)"})
    email = fields.String(required=True, metadata={"description": "Email address"})
    password = fields.String(required=True, load_only=True, metadata={"description": "Password (min 6 chars)"})


class LoginSchema(Schema):
    email = fields.String(required=True, metadata={"description": "Email address"})
    password = fields.String(required=True, load_only=True, metadata={"description": "Password"})


class RoleNestedSchema(Schema):
    id = fields.String(metadata={"description": "Role ID"})
    name = fields.String(metadata={"description": "Role name"})
    permissions = fields.List(fields.String(), metadata={"description": "Granted permissions"})
    is_default = fields.Boolean(metadata={"description": "Auto-assigned to new users"})
    created_at = fields.String(metadata={"description": "ISO timestamp"})


class UserSchema(Schema):
    id = fields.String(metadata={"description": "User ID"})
    username = fields.String(metadata={"description": "Username"})
    email = fields.String(metadata={"description": "Email address"})
    avatar = fields.String(allow_none=True, metadata={"description": "Avatar URL"})
    is_online = fields.Boolean(metadata={"description": "Currently online in app"})
    last_seen = fields.String(allow_none=True, metadata={"description": "ISO timestamp"})
    created_at = fields.String(allow_none=True, metadata={"description": "ISO timestamp"})
    roles = fields.List(fields.Nested(RoleNestedSchema), metadata={"description": "Assigned roles"})
    friends = fields.List(fields.String(), load_default=[], metadata={"description": "Friend user IDs"})


class AuthResponseSchema(Schema):
    user = fields.Nested(UserSchema)
    access_token = fields.String(metadata={"description": "JWT access token"})


class UserResponseSchema(Schema):
    user = fields.Nested(UserSchema)


class ForgotPasswordSchema(Schema):
    email = fields.String(required=True, metadata={"description": "Registered email address"})


class ResetPasswordSchema(Schema):
    token = fields.String(required=True, metadata={"description": "Reset token from email link"})
    new_password = fields.String(required=True, load_only=True, metadata={"description": "New password (min 6 chars)"})


# ── Roles ───────────────────────────────────────────────────

class CreateRoleSchema(Schema):
    name = fields.String(required=True, metadata={"description": "Role name (min 2 chars)"})
    permissions = fields.List(fields.String(), load_default=[], metadata={"description": "Permission names"})
    is_default = fields.Boolean(load_default=False, metadata={"description": "Auto-assign to new users?"})


class UpdateRoleSchema(Schema):
    name = fields.String(metadata={"description": "New role name"})
    permissions = fields.List(fields.String(), metadata={"description": "Updated permissions"})
    is_default = fields.Boolean(metadata={"description": "Auto-assign to new users?"})


class RoleSchema(Schema):
    id = fields.String(metadata={"description": "Role ID"})
    name = fields.String(metadata={"description": "Role name"})
    permissions = fields.List(fields.String(), metadata={"description": "Granted permissions"})
    is_default = fields.Boolean(metadata={"description": "Auto-assigned to new users"})
    created_at = fields.String(metadata={"description": "ISO timestamp"})


class RoleResponseSchema(Schema):
    role = fields.Nested(RoleSchema)


class RoleListSchema(Schema):
    roles = fields.List(fields.Nested(RoleSchema))


class AssignRevokeSchema(Schema):
    user_id = fields.String(required=True, metadata={"description": "User ID"})
    role_id = fields.String(required=True, metadata={"description": "Role ID"})


class PermissionListSchema(Schema):
    permissions = fields.List(fields.String(), metadata={"description": "All valid permission names"})


# ── Servers ─────────────────────────────────────────────────

class CreateServerSchema(Schema):
    name = fields.String(required=True, metadata={"description": "Server name (2-100 chars)"})
    icon = fields.String(allow_none=True, load_default=None, metadata={"description": "Icon URL"})


class UpdateServerSchema(Schema):
    name = fields.String(metadata={"description": "New server name"})
    icon = fields.String(allow_none=True, metadata={"description": "New icon URL"})


class ServerSchema(Schema):
    id = fields.String(metadata={"description": "Server ID"})
    name = fields.String(metadata={"description": "Server name"})
    icon = fields.String(allow_none=True, metadata={"description": "Icon URL"})
    owner_id = fields.String(allow_none=True, metadata={"description": "Owner user ID"})
    is_default = fields.Boolean(metadata={"description": "Is the default server"})
    member_count = fields.Integer(metadata={"description": "Number of members"})
    created_at = fields.String(metadata={"description": "ISO timestamp"})


class ServerResponseSchema(Schema):
    server = fields.Nested(ServerSchema)


class ServerListSchema(Schema):
    servers = fields.List(fields.Nested(ServerSchema))


class MemberSchema(Schema):
    id = fields.String(metadata={"description": "User ID"})
    username = fields.String(metadata={"description": "Username"})
    email = fields.String(metadata={"description": "Email"})
    avatar = fields.String(allow_none=True, metadata={"description": "Avatar URL"})
    is_online = fields.Boolean(metadata={"description": "Currently online"})
    last_seen = fields.String(allow_none=True, metadata={"description": "ISO timestamp"})
    created_at = fields.String(allow_none=True, metadata={"description": "ISO timestamp"})


class MemberListSchema(Schema):
    members = fields.List(fields.Nested(MemberSchema))


# ── Channels ────────────────────────────────────────────────

class CreateChannelSchema(Schema):
    name = fields.String(required=True, metadata={"description": "Channel name (2-100 chars)"})
    type = fields.String(
        load_default="voice",
        metadata={"description": "Channel type: voice or text"},
    )
    position = fields.Integer(
        allow_none=True, load_default=None,
        metadata={"description": "Sort position (auto-assigned if omitted)"},
    )
    user_limit = fields.Integer(
        load_default=0,
        metadata={"description": "Max users (0 = unlimited)"},
    )


class UpdateChannelSchema(Schema):
    name = fields.String(metadata={"description": "New channel name"})
    type = fields.String(metadata={"description": "New channel type"})
    position = fields.Integer(metadata={"description": "New sort position"})
    user_limit = fields.Integer(metadata={"description": "New user limit"})


class ChannelSchema(Schema):
    id = fields.String(metadata={"description": "Channel ID"})
    name = fields.String(metadata={"description": "Channel name"})
    server_id = fields.String(metadata={"description": "Parent server ID"})
    type = fields.String(metadata={"description": "voice or text"})
    position = fields.Integer(metadata={"description": "Sort position"})
    user_limit = fields.Integer(metadata={"description": "Max users (0 = unlimited)"})
    is_default = fields.Boolean(metadata={"description": "Is the default channel"})
    created_at = fields.String(metadata={"description": "ISO timestamp"})


class ChannelResponseSchema(Schema):
    channel = fields.Nested(ChannelSchema)


class ChannelListSchema(Schema):
    channels = fields.List(fields.Nested(ChannelSchema))


# ── Voice ───────────────────────────────────────────────────

class JoinVoiceResponseSchema(Schema):
    token = fields.String(metadata={"description": "Media-server JWT token"})
    url = fields.String(metadata={"description": "Media-server WebSocket URL"})
    room = fields.String(metadata={"description": "Room name on the media server"})


class TrackSchema(Schema):
    sid = fields.String(metadata={"description": "Track session ID"})
    name = fields.String(metadata={"description": "Track name"})
    kind = fields.String(metadata={"description": "audio or video"})
    muted = fields.Boolean(metadata={"description": "Is the track muted"})


class VoiceParticipantSchema(Schema):
    identity = fields.String(metadata={"description": "Participant user ID"})
    name = fields.String(metadata={"description": "Display name"})
    sid = fields.String(metadata={"description": "Participant session ID"})
    state = fields.String(metadata={"description": "Connection state"})
    tracks = fields.List(fields.Nested(TrackSchema), metadata={"description": "Published tracks"})


class ParticipantListSchema(Schema):
    participants = fields.List(fields.Nested(VoiceParticipantSchema))


class MuteRequestSchema(Schema):
    track_sid = fields.String(required=True, metadata={"description": "Track session ID to mute/unmute"})
    muted = fields.Boolean(load_default=True, metadata={"description": "True to mute, False to unmute"})


# ── Invites ─────────────────────────────────────────────────

class CreateInviteSchema(Schema):
    max_uses = fields.Integer(load_default=0, metadata={"description": "Max uses (0 = unlimited)"})
    expires_in_hours = fields.Integer(
        allow_none=True, load_default=None,
        metadata={"description": "Hours until expiry (null = never)"},
    )


class InviteSchema(Schema):
    id = fields.String(metadata={"description": "Invite ID"})
    code = fields.String(metadata={"description": "Invite code"})
    server_id = fields.String(metadata={"description": "Server ID"})
    created_by = fields.String(metadata={"description": "Creator user ID"})
    max_uses = fields.Integer(metadata={"description": "Max uses (0 = unlimited)"})
    uses = fields.Integer(metadata={"description": "Times used"})
    expires_at = fields.String(allow_none=True, metadata={"description": "Expiry ISO timestamp"})
    created_at = fields.String(metadata={"description": "ISO timestamp"})
    # Extra fields from preview
    server_name = fields.String(load_default=None, metadata={"description": "Server name"})
    server_icon = fields.String(allow_none=True, load_default=None, metadata={"description": "Server icon"})
    member_count = fields.Integer(load_default=None, metadata={"description": "Server member count"})


class InviteResponseSchema(Schema):
    invite = fields.Nested(InviteSchema)


class InviteListSchema(Schema):
    invites = fields.List(fields.Nested(InviteSchema))


class InviteAcceptResponseSchema(Schema):
    server = fields.Nested(ServerSchema)
    message = fields.String(metadata={"description": "Success message"})


# ── Messages ─────────────────────────────────────────────────

class SendMessageSchema(Schema):
    content = fields.String(required=True, metadata={"description": "Message content (max 2000 chars)"})


class EditMessageSchema(Schema):
    content = fields.String(required=True, metadata={"description": "New message content"})


class ChatMessageSchema(Schema):
    id = fields.String(metadata={"description": "Message ID"})
    channel_id = fields.String(metadata={"description": "Channel ID"})
    author_id = fields.String(metadata={"description": "Author user ID"})
    author_username = fields.String(allow_none=True, metadata={"description": "Author username"})
    author_avatar = fields.String(allow_none=True, metadata={"description": "Author avatar URL"})
    content = fields.String(metadata={"description": "Message content"})
    created_at = fields.String(metadata={"description": "ISO timestamp"})
    edited_at = fields.String(allow_none=True, metadata={"description": "ISO timestamp of last edit"})


class MessageResponseSchema(Schema):
    message = fields.Nested(ChatMessageSchema)


class MessageListSchema(Schema):
    messages = fields.List(fields.Nested(ChatMessageSchema))


# ── Friends ──────────────────────────────────────────────────

class SendFriendRequestSchema(Schema):
    username = fields.String(required=True, metadata={"description": "Username to send request to"})


class FriendUserSchema(Schema):
    id = fields.String(metadata={"description": "User ID"})
    username = fields.String(metadata={"description": "Username"})
    avatar = fields.String(allow_none=True, metadata={"description": "Avatar URL"})
    is_online = fields.Boolean(metadata={"description": "Currently online"})
    last_seen = fields.String(allow_none=True, metadata={"description": "ISO timestamp"})


class FriendListSchema(Schema):
    friends = fields.List(fields.Nested(FriendUserSchema))


class PendingRequestSchema(Schema):
    id = fields.String(metadata={"description": "Request ID"})
    requester_id = fields.String(metadata={"description": "Requester user ID"})
    addressee_id = fields.String(metadata={"description": "Addressee user ID"})
    status = fields.String(metadata={"description": "Request status"})
    created_at = fields.String(allow_none=True, metadata={"description": "ISO timestamp"})
    user = fields.Nested(FriendUserSchema, metadata={"description": "The other user's info"})


class PendingListSchema(Schema):
    incoming = fields.List(fields.Nested(PendingRequestSchema))
    outgoing = fields.List(fields.Nested(PendingRequestSchema))


class FriendRequestResponseSchema(Schema):
    auto_accepted = fields.Boolean(metadata={"description": "True if request was auto-accepted"})
    request = fields.Nested(PendingRequestSchema, allow_none=True)
    friend = fields.Nested(FriendUserSchema, allow_none=True)


# ── Direct Messages ─────────────────────────────────────────

class SendDMSchema(Schema):
    content = fields.String(required=True, metadata={"description": "Message content (max 2000 chars)"})


class EditDMSchema(Schema):
    content = fields.String(required=True, metadata={"description": "New message content"})


class DMSchema(Schema):
    id = fields.String(metadata={"description": "Message ID"})
    sender_id = fields.String(metadata={"description": "Sender user ID"})
    recipient_id = fields.String(metadata={"description": "Recipient user ID"})
    conversation_key = fields.String(metadata={"description": "Conversation key"})
    content = fields.String(metadata={"description": "Message content"})
    created_at = fields.String(metadata={"description": "ISO timestamp"})
    edited_at = fields.String(allow_none=True, metadata={"description": "ISO timestamp of last edit"})
    is_read = fields.Boolean(metadata={"description": "Has the recipient read it?"})
    sender_username = fields.String(allow_none=True, metadata={"description": "Sender username"})
    sender_avatar = fields.String(allow_none=True, metadata={"description": "Sender avatar URL"})


class DMResponseSchema(Schema):
    message = fields.Nested(DMSchema)


class DMListSchema(Schema):
    messages = fields.List(fields.Nested(DMSchema))


class ConversationSchema(Schema):
    friend = fields.Nested(FriendUserSchema, metadata={"description": "The friend in this conversation"})
    last_message = fields.Nested(DMSchema, metadata={"description": "The latest DM"})
    unread_count = fields.Integer(metadata={"description": "Number of unread messages"})


class ConversationListSchema(Schema):
    conversations = fields.List(fields.Nested(ConversationSchema))
