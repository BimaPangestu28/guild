fn main() {
    // Trigger rebuild when dashboard dist changes
    println!("cargo:rerun-if-changed=dashboard/dist/");
}
