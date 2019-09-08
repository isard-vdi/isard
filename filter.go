package guac

// Filter *
//  * Interface which provides for the filtering of individual instructions. Each
//  * filtered instruction may be allowed through untouched, modified, replaced,
//  * dropped, or explicitly denied.
type Filter interface {

	/**
	 * Applies the filter to the given instruction, returning the original
	 * instruction, a modified version of the original, or null, depending
	 * on the implementation.
	 *
	 * @param instruction The instruction to filter.
	 * @return The original instruction, if the instruction is to be allowed,
	 *         a modified version of the instruction, if the instruction is
	 *         to be overridden, or null, if the instruction is to be dropped.
	 * @throws GuacamoleException If an error occurs filtering the instruction,
	 *                            or if the instruction must be explicitly
	 *                            denied.
	 */
	Filter(instruction Instruction) (ret Instruction, err ExceptionInterface)
}
