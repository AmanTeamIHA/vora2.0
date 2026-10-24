import { ControlBoard } from "@/components/control-board";
import { PlatformControls } from "@/components/platform-controls";
import { StackStatus } from "@/components/stack-status";

export default function AdminHome() {
  return (
    <div className="flex flex-col gap-6">
      <ControlBoard />
      <PlatformControls />
      <StackStatus />
    </div>
  );
}
