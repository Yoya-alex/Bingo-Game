export default function NotificationComponent({ notification }) {
  if (!notification?.message) {
    return null;
  }

  return (
    <div className={`notification show ${notification.type}`}>
      {notification.message}
    </div>
  );
}
