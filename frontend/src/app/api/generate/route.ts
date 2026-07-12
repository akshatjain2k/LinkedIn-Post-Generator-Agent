import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";
import { NextResponse } from "next/server";

// Allow requests to run for up to 5 minutes instead of the default 15s limit on Vercel/Next.js serverless functions.
export const maxDuration = 300;

export async function POST(request: Request) {
  let transport: SSEClientTransport | null = null;
  
  try {
    const { topic } = await request.json();
    if (!topic) {
      return NextResponse.json({ error: "Topic is required" }, { status: 400 });
    }

    // Connect to the local MCP Server (mcp_server.py)
    transport = new SSEClientTransport(new URL("http://127.0.0.1:8000/sse"));
    const client = new Client({
      name: "nextjs-client",
      version: "1.0.0",
    }, {
      capabilities: {}
    });

    await client.connect(transport);

    // Call the create_linkedin_post tool with a 5 minute timeout
    const result = await client.callTool({
      name: "create_linkedin_post",
      arguments: { topic }
    }, undefined, { timeout: 300000 });

    // Clean up
    await transport.close();

    return NextResponse.json(result);
  } catch (error: any) {
    console.error("MCP Error:", error);
    if (transport) {
      try { await transport.close(); } catch (e) {}
    }
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
