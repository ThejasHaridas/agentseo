import { Suspense } from "react";
import AuthScreen from "@/components/AuthScreen";

export const metadata = { title: "Create account" };

export default function RegisterPage() {
  return <Suspense><AuthScreen mode="register" /></Suspense>;
}
