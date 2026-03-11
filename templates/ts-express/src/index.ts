import express, { Request, Response } from "express";
import { PrismaClient } from "@prisma/client";

const app = express();
const prisma = new PrismaClient();
const port = Number(process.env.PORT) || 3000;

app.use(express.json());

app.get("/health", (_req: Request, res: Response) => {
  res.json({ status: "ok" });
});

app.get("/items", async (_req: Request, res: Response) => {
  const items = await prisma.item.findMany();
  res.json(items);
});

app.post("/items", async (req: Request, res: Response) => {
  const { name, description } = req.body;
  if (!name) {
    res.status(400).json({ error: "name is required" });
    return;
  }
  const item = await prisma.item.create({ data: { name, description } });
  res.status(201).json(item);
});

app.get("/items/:id", async (req: Request, res: Response) => {
  const item = await prisma.item.findUnique({ where: { id: Number(req.params.id) } });
  if (!item) {
    res.status(404).json({ error: "not found" });
    return;
  }
  res.json(item);
});

app.put("/items/:id", async (req: Request, res: Response) => {
  const { name, description } = req.body;
  try {
    const item = await prisma.item.update({
      where: { id: Number(req.params.id) },
      data: { name, description },
    });
    res.json(item);
  } catch {
    res.status(404).json({ error: "not found" });
  }
});

app.delete("/items/:id", async (req: Request, res: Response) => {
  try {
    await prisma.item.delete({ where: { id: Number(req.params.id) } });
    res.status(204).send();
  } catch {
    res.status(404).json({ error: "not found" });
  }
});

app.listen(port, () => console.log(`Server running on port ${port}`));
