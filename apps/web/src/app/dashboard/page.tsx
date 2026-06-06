"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const QBO_CONNECT_URL =
  "http://localhost:8000/auth/qbo/connect?firm_id=00000000-0000-0000-0000-000000000001";

export default function DashboardPage() {
  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <Card className="w-full max-w-md text-center">
        <CardHeader>
          <CardTitle>Welcome to CloseMind</CardTitle>
          <CardDescription>
            Connect your QuickBooks account to get started
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-4">
          <a
            href={QBO_CONNECT_URL}
            className="inline-flex h-10 items-center justify-center rounded-md bg-green-600 px-6 text-sm font-medium text-white transition-colors hover:bg-green-700"
          >
            Connect QuickBooks
          </a>
          <p className="text-sm text-muted-foreground">
            You will be redirected to Intuit to authorize access
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
