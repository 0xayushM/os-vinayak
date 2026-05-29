import { redirect } from "next/navigation";

// Root → middleware will redirect to /login if no cookie, or /dashboard if logged in.
// We send to /dashboard and let middleware handle the rest.
export default function Home() {
  redirect("/dashboard");
}
